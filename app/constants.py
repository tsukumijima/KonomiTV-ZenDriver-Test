from typing import Any


# ロギング設定
LOGGING_CONFIG: dict[str, Any] = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        # サーバーログ用のログフォーマッター
        'default': {
            '()': 'uvicorn.logging.DefaultFormatter',
            'datefmt': '%Y/%m/%d %H:%M:%S',
            'format': '[%(asctime)s] %(levelprefix)s %(message)s',
        },
        # サーバーログ (デバッグ) 用のログフォーマッター
        'debug': {
            '()': 'uvicorn.logging.DefaultFormatter',
            'datefmt': '%Y/%m/%d %H:%M:%S',
            'format': '[%(asctime)s] %(levelprefix)s %(pathname)s:%(lineno)s:\n'
            '                                %(message)s',
        },
    },
    'handlers': {
        'default': {
            'formatter': 'default',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
        },
        'debug': {
            'formatter': 'debug',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
        },
    },
    'loggers': {
        'uvicorn': {'level': 'INFO', 'handlers': ['default']},
        'uvicorn.debug': {'level': 'DEBUG', 'handlers': ['debug'], 'propagate': False},
        'uvicorn.error': {'level': 'INFO'},
    },
}
