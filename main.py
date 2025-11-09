import asyncio
from dataclasses import dataclass
from pathlib import Path

import zendriver as zd
from zendriver import cdp


@dataclass
class Cookie:
    """Netscape フォーマットの cookie を表現するデータクラス"""

    domain: str
    path: str
    secure: bool
    expires: int | None
    name: str
    value: str


def parse_netscape_cookie_file(file_path: Path) -> list[Cookie]:
    """
    Netscape フォーマットの cookie ファイルをパースする

    Args:
        file_path: cookie ファイルのパス

    Returns:
        パースされた cookie のリスト
    """
    cookies: list[Cookie] = []
    with file_path.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # コメント行や空行をスキップ
            if not line or line.startswith('#'):
                continue
            # Netscape フォーマット: domain, flag, path, secure, expiration, name, value
            parts = line.split('\t')
            if len(parts) < 7:
                continue
            domain = parts[0]
            # flag (parts[1]) は使用しない
            path = parts[2]
            secure = parts[3] == 'TRUE'
            expires_str = parts[4]
            expires = int(expires_str) if expires_str and expires_str != '0' else None
            name = parts[5]
            value = parts[6]
            cookies.append(
                Cookie(
                    domain=domain,
                    path=path,
                    secure=secure,
                    expires=expires,
                    name=name,
                    value=value,
                )
            )
    return cookies


async def main():
    print('[DEBUG] Starting browser...')
    browser = await zd.start(
        headless=False,
    )
    print('[DEBUG] Browser started.')

    # まず、最初のタブを取得
    page = await browser.get('about:blank')
    print('[DEBUG] Page opened.')

    # cookies.txt を読み込んで cookie を設定
    cookies_txt_path = Path(__file__).parent / 'cookies.txt'
    if cookies_txt_path.exists():
        print('[DEBUG] Loading cookies from cookies.txt...')
        cookies = parse_netscape_cookie_file(cookies_txt_path)
        print(f'[DEBUG] Found {len(cookies)} cookies in cookies.txt')
        # Network ドメインを有効化
        await page.send(cdp.network.enable())
        # 各 cookie を設定
        for cookie in cookies:
            try:
                # expires が None の場合は設定しない（セッション cookie として扱われる）
                expires = None
                if cookie.expires is not None:
                    # TimeSinceEpoch は秒単位の Unix timestamp
                    expires = cdp.network.TimeSinceEpoch(cookie.expires)
                # domain から URL を構築（ドットで始まる場合は除去）
                domain_for_url = cookie.domain.lstrip('.')
                # secure フラグに応じてプロトコルを選択
                protocol = 'https' if cookie.secure else 'http'
                url = f'{protocol}://{domain_for_url}'
                success = await page.send(
                    cdp.network.set_cookie(
                        name=cookie.name,
                        value=cookie.value,
                        url=url,
                        path=cookie.path,
                        secure=cookie.secure if cookie.secure else None,
                        expires=expires,
                    )
                )
                if success:
                    print(f'[DEBUG] Cookie set: {cookie.name} for {cookie.domain}')
                else:
                    print(f'[DEBUG] Failed to set cookie: {cookie.name} for {cookie.domain}')
            except Exception as e:
                print(f'[DEBUG] Error setting cookie {cookie.name}: {e}')
        print('[DEBUG] Cookies loaded.')
    else:
        print('[DEBUG] cookies.txt not found, skipping cookie loading.')

    # Debugger を有効化
    await page.send(cdp.debugger.enable())
    print('[DEBUG] DevTools debugger enabled.')

    # setup.js の内容を読み込む
    setup_js_path = Path(__file__).parent / 'setup.js'
    setup_js_code = setup_js_path.read_text(encoding='utf-8')

    # セットアップ処理の完了を把握するための Future
    setup_complete_future = asyncio.get_running_loop().create_future()

    # Debugger.paused イベントをリッスン
    async def on_paused(event: cdp.debugger.Paused) -> None:
        print('[DEBUG] Pause event fired.')
        try:
            # ブレークポイント停止中に setup.js のコードを設置する
            # await_promise は指定しない（デフォルトは False）ので、スクリプトは設置されるが待機しない
            _, exception = await page.send(
                cdp.runtime.evaluate(
                    expression=setup_js_code,
                    return_by_value=True,
                )
            )
            print('[DEBUG] setup.js executed.')
            if exception is not None:
                # 実行中になんらかの例外が発生した場合
                setup_complete_future.set_exception(Exception(f'Failed to execute setup.js: {exception}'))
        except Exception as e:
            setup_complete_future.set_exception(e)
        finally:
            # 実行を再開（再開後、setup.js 内の window.__setupPromise が実行される）
            await page.send(cdp.debugger.resume())
            # 再開後、window.__setupPromise が解決されるまで待つ
            try:
                await asyncio.sleep(1)  # 再開後に少し待つ (でないと window.__setupPromise がセットされていない)
                print('[DEBUG] Waiting for setup.js to be resolved...')
                result, exception = await page.send(
                    cdp.runtime.evaluate(
                        expression='window.__setupPromise',
                        await_promise=True,
                        return_by_value=True,
                    )
                )
                print('[DEBUG] setup.js evaluated.')
                if exception is not None:
                    setup_complete_future.set_exception(Exception(f'Failed to wait for setup promise: {exception}'))
                else:
                    # result.value が厳密に True であることを確認（undefined の可能性を排除）
                    if result.value is True:
                        print('[DEBUG] setup.js resolved: true (strictly verified)')
                        setup_complete_future.set_result(True)
                    else:
                        setup_complete_future.set_exception(
                            Exception(f'Setup promise did not return true. Got: {result.value}')
                        )
            except Exception as e:
                setup_complete_future.set_exception(e)

    page.add_handler(cdp.debugger.Paused, on_paused)

    # x.com の main.js の1行目にブレークポイントを設定
    # ブレークポイントが発火すると on_paused ハンドラーが呼ばれ、setup.js が実行される
    breakpoint_id, _ = await page.send(
        cdp.debugger.set_breakpoint_by_url(
            line_number=0,  # 0-based なので 1行目は 0
            url_regex=r'.*main.*\.js',  # main.js をマッチさせる正規表現
        )
    )
    print(f'[DEBUG] Breakpoint set. id: {breakpoint_id}')

    # x.com に移動
    page = await browser.get('https://x.com/home')
    await page.activate()

    # setup.js に記述したセットアップ処理が完了するまで待つ
    try:
        await asyncio.wait_for(setup_complete_future, timeout=15.0)
        print('[DEBUG] Setup completed successfully.')
    except TimeoutError:
        print('[DEBUG] Timeout: Breakpoint was not hit or setup did not complete within 30 seconds.')
    except Exception as e:
        print(f'[DEBUG] Error during setup: {e}')

    await asyncio.sleep(10)

    # Debugger を無効化
    await page.send(cdp.debugger.disable())
    print('[DEBUG] Debugger disabled.')

    # ブラウザを停止
    print('[DEBUG] Waiting for browser to terminate...')
    try:
        await browser.stop()
        print('[DEBUG] Browser terminated.')
    except Exception as e:
        print(f'[DEBUG] Error while terminating browser: {e}')


if __name__ == '__main__':
    asyncio.run(main())
