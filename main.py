import asyncio
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint
from typing import Any

import zendriver as zd
from zendriver import Tab, cdp


# Twitter API のエラーコードとエラーメッセージの対応表
# 実際に返ってくる可能性があるものだけ
# ref: https://developer.twitter.com/ja/docs/basics/response-codes
ERROR_MESSAGES: dict[int, str] = {
    32: 'Twitter アカウントの認証に失敗しました。もう一度連携し直してください。',
    63: 'Twitter アカウントが凍結またはロックされています。',
    64: 'Twitter アカウントが凍結またはロックされています。',
    88: 'Twitter API エンドポイントのレート制限を超えました。',
    89: 'Twitter アクセストークンの有効期限が切れています。',
    99: 'Twitter OAuth クレデンシャルの認証に失敗しました。',
    131: 'Twitter でサーバーエラーが発生しています。',
    135: 'Twitter アカウントの認証に失敗しました。もう一度連携し直してください。',
    139: 'すでにいいねされています。',
    144: 'ツイートが非公開かすでに削除されています。',
    179: 'フォローしていない非公開アカウントのツイートは表示できません。',
    185: 'ツイート数の上限に達しました。',
    186: 'ツイートが長過ぎます。',
    187: 'ツイートが重複しています。',
    226: 'ツイートが自動化されたスパムと判定されました。',
    261: 'Twitter API アプリケーションが凍結されています。',
    326: 'Twitter アカウントが一時的にロックされています。',
    327: 'すでにリツイートされています。',
    328: 'このツイートではリツイートは許可されていません。',
    416: 'Twitter API アプリケーションが無効化されています。',
}


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
        file_path (Path): cookie ファイルのパス

    Returns:
        list[Cookie]: パースされた cookie のリスト
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


def convert_to_cookie_params(cookies: list[Cookie]) -> list[cdp.network.CookieParam]:
    """
    Netscape フォーマットの Cookie を CookieParam に変換する

    Args:
        cookies (list[Cookie]): Netscape フォーマットの cookie のリスト

    Returns:
        list[cdp.network.CookieParam]: CookieParam のリスト
    """

    cookie_params: list[cdp.network.CookieParam] = []
    for cookie in cookies:
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
        cookie_params.append(
            cdp.network.CookieParam(
                name=cookie.name,
                value=cookie.value,
                url=url,
                domain=cookie.domain if cookie.domain else None,
                path=cookie.path if cookie.path else None,
                secure=cookie.secure,
                expires=expires,
            )
        )
    return cookie_params


async def save_twitter_cookies_to_file(browser: zd.Browser, file_path: Path) -> None:
    """
    ブラウザから x.com 関連の cookie を取得して Netscape フォーマットのファイルに保存する

    Args:
        browser (zd.Browser): ZenDriver の Browser インスタンス
        file_path (Path): 保存先のファイルパス
    """

    # 全ての cookie を取得
    all_cookies = await browser.cookies.get_all(requests_cookie_format=False)
    # requests_cookie_format=False なので cdp.network.Cookie のリストが返される
    # x.com や twitter.com に関連する cookie をフィルタリング
    twitter_cookies: list[cdp.network.Cookie] = [
        c
        for c in all_cookies
        if isinstance(c, cdp.network.Cookie) and ('x.com' in c.domain or 'twitter.com' in c.domain)
    ]

    if not twitter_cookies:
        print('[DEBUG] No Twitter-related cookies found, skipping save.')
        return

    # Netscape フォーマットでファイルに保存
    with file_path.open('w', encoding='utf-8') as f:
        # Netscape フォーマットのヘッダーを書き込む
        f.write('# Netscape HTTP Cookie File\n')
        f.write('# https://curl.haxx.se/rfc/cookie_spec.html\n')
        f.write('# This is a generated file! Do not edit.\n')
        f.write('\n')
        # 各 cookie を Netscape フォーマットで書き込む
        for cookie in twitter_cookies:
            # domain がドットで始まる場合は flag を TRUE、そうでなければ FALSE
            flag = 'TRUE' if cookie.domain.startswith('.') else 'FALSE'
            # secure フラグを TRUE/FALSE に変換
            secure_str = 'TRUE' if cookie.secure else 'FALSE'
            # expires が None の場合は 0（セッション cookie）を設定
            expires_value = int(cookie.expires) if cookie.expires is not None else 0
            # Netscape フォーマット: domain, flag, path, secure, expiration, name, value
            netscape_line = (
                f'{cookie.domain}\t{flag}\t{cookie.path}\t{secure_str}\t{expires_value}\t{cookie.name}\t{cookie.value}'
            )
            f.write(f'{netscape_line}\n')

    print(f'[DEBUG] Successfully saved {len(twitter_cookies)} cookies to cookies.txt.')


async def invokeGraphQLAPI(
    page: Tab,
    endpoint_name: str,
    variables: dict[str, Any],
    additional_flags: dict[str, Any] | None = None,
    error_message_prefix: str = 'Twitter API の操作に失敗しました。',
) -> dict[str, Any] | str:
    """
    Twitter Web App の GraphQL API に HTTP リクエストを送信する
    実際には GraphQL と言いつつペイロードで JSON を渡しているので謎… (本当に GraphQL なのか？)

    Args:
        page (Tab): ZenDriver の Tab インスタンス
        endpoint_name (str): GraphQL API のエンドポイント名 (例: 'CreateTweet')
        variables (dict[str, Any]): GraphQL API へのリクエストパラメータ (ペイロードのうち "variables" の部分)
        additional_flags (dict[str, Any] | None): 追加のフラグ（オプション）
        error_message_prefix (str): エラー発生時に付与する prefix (例: 'ツイートの送信に失敗しました。')

    Returns:
        dict[str, Any] | str: GraphQL API のレスポンス (失敗時は日本語のエラーメッセージを返す)
    """

    # JavaScript コードを構築（JSON を文字列化して渡す）
    # エラー処理は JavaScript 側で完結し、シリアライズ可能なデータを返す
    additional_flags_json = json.dumps(additional_flags, ensure_ascii=False) if additional_flags is not None else 'null'
    js_code = f"""
    (async () => {{
        const requestPayload = {json.dumps(variables, ensure_ascii=False)};
        const additionalFlags = {additional_flags_json};
        const result = await window.__invokeGraphQLAPI('{endpoint_name}', requestPayload, additionalFlags);
        console.log('window.__invokeGraphQLAPI() result:', result);
        return result;
    }})()
    """

    # Twitter GraphQL API に HTTP リクエストを送信する
    try:
        result, exception = await page.send(
            cdp.runtime.evaluate(
                expression=js_code,
                await_promise=True,
                return_by_value=True,
            )
        )

        # 最低限のバリデーション
        if exception is not None:
            print('[ERROR] [TwitterGraphQLAPI] Failed to connect to Twitter GraphQL API.')
            return error_message_prefix + 'Twitter API に接続できませんでした。'
        if result.value is None:
            print('[ERROR] [TwitterGraphQLAPI] Response is None.')
            return error_message_prefix + 'Twitter API から不正なレスポンスが返されました。'

        # JavaScript 側から返された結果を取得
        result_value = result.value
        if not isinstance(result_value, dict):
            print('[ERROR] [TwitterGraphQLAPI] Response is not a dict.')
            return error_message_prefix + 'Twitter API から不正なレスポンスが返されました。'

        # API レスポンスを取得
        parsed_response = result_value.get('parsedResponse')
        status_code = result_value.get('statusCode')
        response_text = result_value.get('responseText')
        headers = result_value.get('headers')
        request_error = result_value.get('requestError')

        # リクエストエラーが発生した場合（接続エラー）
        if request_error:
            print('[ERROR] [TwitterGraphQLAPI] Failed to connect to Twitter GraphQL API.')
            return error_message_prefix + 'Twitter API に接続できませんでした。'

        # HTTP ステータスコードが 200 系以外の場合
        if status_code is not None and not (200 <= status_code < 300):
            print(f'[ERROR] [TwitterGraphQLAPI] Failed to invoke GraphQL API. (HTTP Error {status_code})')
            if response_text:
                print(f'[ERROR] [TwitterGraphQLAPI] Response: {response_text}')
            return error_message_prefix + f'Twitter API から HTTP {status_code} エラーが返されました。'

        # JSON でないレスポンスが返ってきた場合
        # charset=utf-8 が付いている場合もあるので完全一致ではなく部分一致で判定
        if headers and isinstance(headers, dict):
            content_type = headers.get('content-type', '')
            if content_type and 'application/json' not in content_type:
                print('[ERROR] [TwitterGraphQLAPI] Response is not JSON.')
                return error_message_prefix + 'Twitter API から不正なレスポンスが返されました。'

        # レスポンスを JSON としてパース
        response_json: dict[str, Any] | None = None
        if parsed_response is not None:
            # JavaScript 側で既にパース済み
            response_json = parsed_response
        elif response_text:
            # JavaScript 側でパースに失敗した場合、Python 側で再試行
            try:
                response_json = json.loads(response_text)
            except Exception:
                print('[ERROR] [TwitterGraphQLAPI] Failed to parse response as JSON.')
                # 注: exc_info の代わりに traceback を出力
                traceback.print_exc()
                return error_message_prefix + 'Twitter API のレスポンスを JSON としてパースできませんでした。'

        if response_json is None:
            print('[ERROR] [TwitterGraphQLAPI] Failed to parse response as JSON.')
            return error_message_prefix + 'Twitter API のレスポンスを JSON としてパースできませんでした。'

        # API レスポンスにエラーが含まれていて、かつ data キーが存在しない場合
        # API レスポンスは Twitter の仕様変更で変わりうるので、ここで判定されなかったと言ってエラーでないとは限らない
        # なぜか正常にレスポンスが含まれているのにエラーも返ってくる場合があるので、その場合は（致命的な）エラーではないと判断する
        if 'errors' in response_json and 'data' not in response_json:
            # Twitter API のエラーコードとエラーメッセージを取得
            # このエラーコードは API v1.1 の頃と変わっていない
            response_error_code = response_json['errors'][0]['code']
            response_error_message = response_json['errors'][0]['message']

            # 想定外のエラーコードが返ってきた場合のエラーメッセージ
            alternative_error_message = f'Code: {response_error_code} / Message: {response_error_message}'
            print(f'[ERROR] [TwitterGraphQLAPI] Failed to invoke GraphQL API ({alternative_error_message})')

            # エラーコードに対応するエラーメッセージを返し、対応するものがない場合は alternative_error_message を返す
            return error_message_prefix + ERROR_MESSAGES.get(response_error_code, alternative_error_message)

        # API レスポンスにエラーが含まれていないが、'data' キーが存在しない場合
        # 実装時点の GraphQL API は必ず成功時は 'data' キーの下にレスポンスが格納されるはず
        # もし 'data' キーが存在しない場合は、API 仕様が変更されている可能性がある
        if 'data' not in response_json:
            print('[ERROR] [TwitterGraphQLAPI] Response does not have "data" key.')
            return (
                error_message_prefix
                + 'Twitter API のレスポンスに "data" キーが存在しません。開発者に修正を依頼してください。'
            )

        # ここまで来たら (中身のデータ構造はともかく) API レスポンスの取得には成功しているはず
        return response_json['data']

    # 接続エラー（サーバーメンテナンスやタイムアウトなど）
    except Exception:
        print('[ERROR] [TwitterGraphQLAPI] Failed to connect to Twitter GraphQL API.')
        # 注: exc_info の代わりに traceback を出力
        traceback.print_exc()
        return error_message_prefix + 'Twitter API に接続できませんでした。'


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
        # Netscape フォーマットの Cookie を CookieParam に変換
        cookie_params = convert_to_cookie_params(cookies)
        # CookieJar を使って一括で設定（高レベル API）
        try:
            await browser.cookies.set_all(cookie_params)
            print(f'[DEBUG] Successfully set {len(cookie_params)} cookies.')
        except Exception as e:
            print(f'[DEBUG] Error setting cookies: {e}')
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
    ## x.com/home だと万が一 Cookie セッションが revoke されている場合にログインモーダルが表示されて
    ## セットアップが解決できないっぽいので、ログイン前の画面がそのまま出てくる x.com/ 直下である必要がある
    page = await browser.get('https://x.com/')
    await page.activate()

    # setup.js に記述したセットアップ処理が完了するまで待つ
    try:
        await asyncio.wait_for(setup_complete_future, timeout=15.0)
        print('[DEBUG] Setup completed successfully.')
    except TimeoutError:
        print('[DEBUG] Timeout: Breakpoint was not hit or setup did not complete within 30 seconds.')
        return
    except Exception as e:
        print(f'[DEBUG] Error during setup: {e}')
        return

    await asyncio.sleep(3)

    # CreateTweet API を呼び出す
    # print('[DEBUG] Calling CreateTweet API...')
    # result = await invokeGraphQLAPI(
    #     page=page,
    #     endpoint_name='CreateTweet',
    #     variables={
    #         'tweet_text': f'Hello, World! {datetime.now().isoformat()}',
    #         'dark_request': False,
    #         'media': {'media_entities': [], 'possibly_sensitive': False},
    #         'semantic_annotation_ids': [],
    #         'disallowed_reply_options': None,
    #     },
    #     error_message_prefix='ツイートの送信に失敗しました。',
    # )
    # if isinstance(result, str):
    #     # エラーメッセージが返された場合
    #     print('[DEBUG] CreateTweet API call failed.')
    #     print(f'[DEBUG] Error: {result}')
    # else:
    #     # 成功時はレスポンスデータが返される
    #     print('[DEBUG] CreateTweet API call succeeded.')
    #     print('[DEBUG] Result:')
    #     pprint(result)

    # await asyncio.sleep(110)

    # HomeLatestTimeline API を呼び出す
    print('[DEBUG] Calling HomeLatestTimeline API...')
    result = await invokeGraphQLAPI(
        page=page,
        endpoint_name='HomeLatestTimeline',
        variables={
            'count': 20,
            'includePromotedContent': True,
            'latestControlAvailable': True,
            'requestContext': 'launch',
            'seenTweetIds': [],
        },
        error_message_prefix='ツイートの送信に失敗しました。',
    )
    if isinstance(result, str):
        # エラーメッセージが返された場合
        print('[DEBUG] HomeLatestTimeline API call failed.')
        print(f'[DEBUG] Error: {result}')
    else:
        # 成功時はレスポンスデータが返される
        print('[DEBUG] HomeLatestTimeline API call succeeded.')
        print('[DEBUG] Result:')
        pprint(result)

    await asyncio.sleep(110)

    # ブラウザ停止前に x.com 関連の cookie を取得して cookies.txt を更新
    print('[DEBUG] Saving cookies to cookies.txt...')
    try:
        cookies_txt_path = Path(__file__).parent / 'cookies.txt'
        await save_twitter_cookies_to_file(browser, cookies_txt_path)
    except Exception as e:
        print(f'[DEBUG] Error saving cookies: {e}')
        traceback.print_exc()

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
