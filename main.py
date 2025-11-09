import asyncio

import zendriver as zd
from zendriver import cdp


async def main():
    browser = await zd.start(
        headless=False,
    )

    # ページを取得する前に、スクリプトを注入する必要があります
    # まず、最初のタブを取得します
    page = await browser.get('about:blank')

    # ページロード前に実行されるスクリプトを注入します
    # このスクリプトは、HTML 内の JavaScript が解析されて実行されるタイミングで
    # window.__INITIAL_STATE__ が設定されるのを待ち、値を取得します
    script_source = '''
        (function() {
            // window.__INITIAL_STATE__ が設定されるのを待つ関数
            function captureFeatureFlags() {
                try {
                    // window.__INITIAL_STATE__ が存在し、featureSwitch.defaultConfig が設定されているか確認
                    if (window.__INITIAL_STATE__ &&
                        window.__INITIAL_STATE__["featureSwitch"] &&
                        window.__INITIAL_STATE__["featureSwitch"]["defaultConfig"]) {

                        // 値を取得して window オブジェクトに保存
                        window.__zendriver_captured_feature_flags = {
                            success: true,
                            timestamp: Date.now(),
                            featureFlags: window.__INITIAL_STATE__["featureSwitch"]["defaultConfig"]
                        };

                        // デバッグ用ログ（必要に応じて）
                        console.log('[Zendriver] Feature flags captured:', window.__zendriver_captured_feature_flags);
                        return;
                    }
                } catch (e) {
                    // エラーが発生した場合は記録
                    window.__zendriver_captured_feature_flags = {
                        success: false,
                        error: e.toString(),
                        timestamp: Date.now()
                    };
                    console.error('[Zendriver] Error capturing feature flags:', e);
                    return;
                }

                // まだ設定されていない場合は、少し待ってから再試行
                // DOMContentLoaded のタイミングで確認
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', function() {
                        setTimeout(captureFeatureFlags, 100);
                    });
                } else {
                    // すでに DOMContentLoaded が発火している場合は、短い間隔でポーリング
                    let attempts = 0;
                    const maxAttempts = 50; // 最大5秒間（100ms * 50）
                    const interval = setInterval(function() {
                        attempts++;
                        if (window.__INITIAL_STATE__ &&
                            window.__INITIAL_STATE__["featureSwitch"] &&
                            window.__INITIAL_STATE__["featureSwitch"]["defaultConfig"]) {
                            clearInterval(interval);
                            captureFeatureFlags();
                        } else if (attempts >= maxAttempts) {
                            clearInterval(interval);
                            window.__zendriver_captured_feature_flags = {
                                success: false,
                                error: 'Timeout: window.__INITIAL_STATE__ not found within timeout period',
                                timestamp: Date.now()
                            };
                        }
                    }, 100);
                }
            }

            // 初期化: まず即座に確認を試みる
            captureFeatureFlags();
        })();
    '''

    # スクリプトを注入します
    script_id = await page.send(
        cdp.page.add_script_to_evaluate_on_new_document(
            source=script_source,
            run_immediately=False,  # false の場合、新しいドキュメントが作成されたときに実行されます
        )
    )
    print(f'Injected script ID: {script_id}')

    # x.com に移動します（スクリプトが自動的に実行されます）
    page = await browser.get('https://x.com')
    await page.activate()

    # window.__INITIAL_STATE__ が設定されるのを待つため、少し待機します
    # HTML 内の JavaScript が解析・実行される時間を考慮
    await asyncio.sleep(3)

    # 注入したスクリプトで取得した feature flags を取得します
    try:
        result = await page.evaluate('window.__zendriver_captured_feature_flags')
        # result は return_by_value=True がデフォルトなので、通常は dict や None が返される
        if result and isinstance(result, dict):
            if result.get('success') is True:
                feature_flags = result.get('featureFlags')
                print(f'Successfully captured feature flags: {feature_flags}')
                # 必要に応じて、feature flags をさらに処理できます
            else:
                print(f'Failed to capture feature flags: {result.get("error")}')
        else:
            print('Feature flags not captured yet. window.__zendriver_captured_feature_flags is not set.')
    except Exception as e:
        print(f'Error getting feature flags: {e}')

    await asyncio.sleep(5)
    await browser.stop()


if __name__ == '__main__':
    asyncio.run(main())
