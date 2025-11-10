import asyncio
from datetime import datetime
from pathlib import Path
from pprint import pprint

from app import logging
from app.TwitterAccount import TwitterAccount
from app.TwitterGraphQLAPI import TwitterGraphQLAPI


async def main():
    logging.info('Starting test...')

    # cookies.txt を読み込む
    cookies_txt_path = Path(__file__).parent / 'cookies.txt'
    cookies_txt_content = ''
    if cookies_txt_path.exists():
        cookies_txt_content = cookies_txt_path.read_text(encoding='utf-8')
        logging.info('Loaded cookies.txt')
    else:
        logging.info('cookies.txt not found, using empty cookies')

    # TwitterAccount インスタンスを作成
    # access_token は "COOKIES_TXT" 固定、access_token_secret に cookies.txt の内容を入れる
    twitter_account = TwitterAccount()
    twitter_account.id = 1
    twitter_account.name = 'Demo Account'
    twitter_account.screen_name = 'demo_account'
    twitter_account.icon_url = 'https://example.com/icon.png'
    twitter_account.access_token = 'COOKIES_TXT'
    twitter_account.access_token_secret = cookies_txt_content

    # TwitterGraphQLAPI インスタンスを取得（シングルトン）
    api = TwitterGraphQLAPI(twitter_account)

    # 現在のログイン中ユーザー情報取得 API を呼び出す
    logging.info('Calling Viewer API...')
    result = await api.fetchLoggedViewer()
    if isinstance(result, str):
        # エラーメッセージが返された場合
        logging.error(f'Viewer API call failed: {result}')
    else:
        # 成功時はレスポンスデータが返される
        logging.info('Viewer API call succeeded.')
        logging.info('Result:')
        pprint(result)

    # CreateTweet API を呼び出す
    logging.info('Calling CreateTweet API...')
    result = await api.createTweet(
        tweet='Hello, world!' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    if isinstance(result, str):
        # エラーメッセージが返された場合
        logging.error(f'CreateTweet API call failed: {result}')
    else:
        # 成功時はレスポンスデータが返される
        logging.info('CreateTweet API call succeeded.')
        logging.info('Result:')
        pprint(result)

    # ブラウザが自動的にシャットダウンされるまでしばらく待つ
    await asyncio.sleep(35)

    # ブラウザ停止前に x.com 関連の Cookie を取得して cookies.txt を更新
    logging.info('Saving cookies to cookies.txt...')
    try:
        # TwitterAccount.access_token_secret に最新の Cookie がセットされているはず
        updated_cookies_content = twitter_account.access_token_secret
        cookies_txt_path.write_text(updated_cookies_content, encoding='utf-8')
        logging.info('Successfully saved cookies to cookies.txt')
    except Exception as ex:
        logging.error(f'Error saving cookies: {ex}', exc_info=ex)

    logging.info('Test completed.')


if __name__ == '__main__':
    asyncio.run(main())
