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
    window.__invokeGraphQLAPI = (operationName, requestPayload, additionalFlags = null) => {
        // operationName から operationInfo を取得
        const operationInfo = operationInfoMap[operationName]
        // HTTP リクエストを実行
        // X-Client-Transaction-ID や各ヘッダーの付与はすべて内部で行われる
        if (additionalFlags) {
            // 第三引数はおそらくサーバーからエラーが返された際に致命的なエラーかをチェックする関数
            return apiClient.graphQL(operationInfo, requestPayload, () => false, additionalFlags)
        } else {
            return apiClient.graphQL(operationInfo, requestPayload);
        }
    }

    return true;
})();
