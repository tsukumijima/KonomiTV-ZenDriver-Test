window.__setupPromise = (async () => {
    // 以下の実装を強く参考にした (thanks to @fa0311 !!)
    // ref: https://gist.github.com/fa0311/f36b00d36d6c4cf9e73c0dd5aefe3516

    // operationInfo を収集する必要がある operationName のセット
    const requiredOperationNames = new Set([
        'CreateTweet',
        'CreateRetweet',
        'DeleteRetweet',
        'FavoriteTweet',
        'UnfavoriteTweet',
        'HomeLatestTimeline',
        'SearchTimeline',
    ]);

    // GraphQL API の operationInfo を収集し、キー: operationName, 値: operationInfo の Map を作る
    const operationInfoMap = await new Promise((resolve) => {
        const collectedOperationNames = new Set();
        const operationInfoMap = {};
        // オリジナルの Function.prototype.call を保存
        const originalCall = Function.prototype.call;
        // Function.prototype.call を上書きする
        Function.prototype.call = function (thisArg, ...args) {
            const module = args[0];
            const ret = originalCall.apply(this, [thisArg, ...args]);
            try {
                const exp = module.exports;
                if (exp.operationName) {
                    operationInfoMap[exp.operationName] = exp;
                    collectedOperationNames.add(exp.operationName);
                    // 必要な operationInfo が全て揃ったかチェック
                    const isAllCollected = Array.from(requiredOperationNames).every(
                        name => collectedOperationNames.has(name)
                    );
                    if (isAllCollected) {
                        // Function.prototype.call を元に戻す
                        Function.prototype.call = originalCall;
                        resolve(operationInfoMap);
                    }
                }
            } catch (_) {}
            return ret;
        };
    });
    console.log("operationInfoMap:", operationInfoMap);

    // Twitter Web App が内部で使用している API クライアント実装のオブジェクトを収集
    const apiClient = await new Promise((resolve) => {
        // オリジナルの Function.prototype.apply を保存
        const __origApply = Function.prototype.apply;
        // Function.prototype.apply を上書きする
        Function.prototype.apply = function (thisArg, argsArray) {
            if (thisArg && typeof thisArg === 'object' && thisArg.dispatch === this) {
                // Function.prototype.apply を元に戻す
                Function.prototype.apply = __origApply;
                resolve(thisArg);
            }
            return __origApply.call(this, thisArg, argsArray);
        };
    });
    console.log("apiClient:", apiClient);

    // API クライアントのラッパーを作成し、これを window オブジェクトに公開する
    window.__invokeGraphQLAPI = async (operationName, requestPayload, additionalFlags = null) => {
        // オリジナルの XMLHttpRequest を保存
        const OriginalXHR = window.XMLHttpRequest;
        // XHR のフックで取得する生の API レスポンスを格納するオブジェクト
        const xhrData = {
            rawResponse: null,
            rawResponseText: null,
            rawStatus: null,
            rawStatusText: null,
            rawHeaders: null,
            xhrError: null,
        };
        // XHR をフックして生の API レスポンスを取得する
        window.XMLHttpRequest = function() {
            const xhr = new OriginalXHR();
            const originalOpen = xhr.open.bind(xhr);
            const originalSend = xhr.send.bind(xhr);
            xhr.open = function(method, url, ...args) {
                // GraphQL API のエンドポイントかどうかを判定
                if (url && url.includes('/graphql/')) {
                    // onreadystatechange をフック
                    xhr.addEventListener('readystatechange', function() {
                        if (xhr.readyState === 4) {
                            xhrData.rawStatus = xhr.status;
                            xhrData.rawStatusText = xhr.statusText;
                            xhrData.rawResponseText = xhr.responseText;
                            xhrData.rawHeaders = {};
                            // レスポンスヘッダーを取得
                            const headerString = xhr.getAllResponseHeaders();
                            if (headerString) {
                                const headerPairs = headerString.trim().split('\r\n');
                                for (const headerPair of headerPairs) {
                                    const [key, value] = headerPair.split(': ');
                                    if (key && value) {
                                        xhrData.rawHeaders[key.toLowerCase()] = value;
                                    }
                                }
                            }
                            // レスポンスをパース
                            try {
                                if (xhrData.rawResponseText) {
                                    xhrData.rawResponse = JSON.parse(xhrData.rawResponseText);
                                }
                            } catch (e) {
                                // JSON パースに失敗した場合は rawResponseText をそのまま保持
                                xhrData.rawResponse = null;
                            }
                        }
                    });
                    // onerror をフック
                    xhr.addEventListener('error', function() {
                        xhrData.xhrError = 'XHR request failed';
                    });
                    // ontimeout をフック
                    xhr.addEventListener('timeout', function() {
                        xhrData.xhrError = 'XHR request timeout';
                    });
                }
                return originalOpen(method, url, ...args);
            };
            xhr.send = function(...args) {
                return originalSend(...args);
            };
            return xhr;
        };
        // XMLHttpRequest のプロトタイプをコピー
        window.XMLHttpRequest.prototype = OriginalXHR.prototype;
        try {
            // operationName から operationInfo を取得
            const operationInfo = operationInfoMap[operationName]
            // HTTP リクエストを実行
            // X-Client-Transaction-ID や各ヘッダーの付与はすべて内部で行われる
            let apiResult;
            if (additionalFlags) {
                // 第三引数はおそらくサーバーからエラーが返された際に致命的なエラーかをチェックする関数
                apiResult = await apiClient.graphQL(operationInfo, requestPayload, () => false, additionalFlags);
            } else {
                apiResult = await apiClient.graphQL(operationInfo, requestPayload);
            }
            // XMLHttpRequest を元に戻す
            window.XMLHttpRequest = OriginalXHR;
            // 生のレスポンスを返す
            return {
                success: true,
                rawResponse: xhrData.rawResponse,
                rawResponseText: xhrData.rawResponseText,
                rawStatus: xhrData.rawStatus,
                rawStatusText: xhrData.rawStatusText,
                rawHeaders: xhrData.rawHeaders,
                apiResult: apiResult,
            };
        } catch (error) {
            // XMLHttpRequest を元に戻す
            window.XMLHttpRequest = OriginalXHR;
            // エラーが発生した場合、生のレスポンスがあればそれを含めて返す
            return {
                success: false,
                error: {
                    message: error.message || error.toString(),
                    name: error.name,
                    stack: error.stack,
                },
                rawResponse: xhrData.rawResponse,
                rawResponseText: xhrData.rawResponseText,
                rawStatus: xhrData.rawStatus,
                rawStatusText: xhrData.rawStatusText,
                rawHeaders: xhrData.rawHeaders,
                xhrError: xhrData.xhrError,
            };
        }
    }

    return true;
})();
