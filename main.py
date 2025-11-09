import asyncio
from pathlib import Path

import zendriver as zd
from zendriver import cdp


async def main():
    browser = await zd.start(
        headless=False,
    )
    print('[DEBUG] Browser started.')

    # まず、最初のタブを取得
    page = await browser.get('about:blank')
    print('[DEBUG] Page opened.')

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
                setup_complete_future.set_exception(
                    Exception(f'Failed to execute setup.js: {exception}')
                )
        except Exception as e:
            setup_complete_future.set_exception(e)
        finally:
            # 実行を再開（再開後、setup.js 内の window.__setupPromise が実行される）
            await page.send(cdp.debugger.resume())
            # 再開後、window.__setupPromise が解決されるまで待つ
            try:
                await asyncio.sleep(0.1)  # 再開後に少し待つ
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
                    setup_complete_future.set_exception(
                        Exception(f'Failed to wait for setup promise: {exception}')
                    )
                else:
                    print('[DEBUG] setup.js resolved:', result)
                    setup_complete_future.set_result(True)
            except Exception as e:
                setup_complete_future.set_exception(e)

    page.add_handler(cdp.debugger.Paused, on_paused)

    # main.js の1行目にブレークポイントを設定
    # x.com の main.js は通常 /main.*\.js のようなパスにある
    breakpoint_id, locations = await page.send(
        cdp.debugger.set_breakpoint_by_url(
            line_number=0,  # 0-based なので 1行目は 0
            url_regex=r'.*main.*\.js',  # main.js をマッチさせる正規表現
        )
    )
    print(f'[DEBUG] Breakpoint set: {breakpoint_id}, locations: {len(locations)}')

    # x.com に移動
    page = await browser.get('https://x.com')
    await page.activate()

    # ブレークポイントで停止してセットアップ処理が完了するのを待つ
    try:
        await asyncio.wait_for(setup_complete_future, timeout=30.0)
        print('Setup completed successfully')
    except TimeoutError:
        print('Timeout: Breakpoint was not hit or setup did not complete within 30 seconds')
    except Exception as e:
        print(f'Error during setup: {e}')

    # Debugger を無効化
    await page.send(cdp.debugger.disable())
    print('Debugger disabled')

    await asyncio.sleep(5)
    await browser.stop()


if __name__ == '__main__':
    asyncio.run(main())
