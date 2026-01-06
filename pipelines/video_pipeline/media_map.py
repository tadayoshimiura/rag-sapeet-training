"""媒体種別の判定と分類。"""
# メディア種別ごとの設定を一元管理する。
MEDIA_MAP = {
    "video": {
        "exts": (".mp4", ".mov", ".mkv", ".webm"),
        "extracted_prefix": "processed/{course_id}/extracted/video/",
        "kb_default_category": None,  # カテゴリ必須
    },
    "pdf": {
        "exts": (".pdf",),
        "extracted_prefix": "processed/{course_id}/extracted/pdf/",
        "kb_default_category": "unknown",  # 必要ならデフォルト
    },
}


def match_media(key: str):
    """キー（パス）から対応するメディア種別を返す。該当なしならNone。"""
    lower = key.lower()
    for media, conf in MEDIA_MAP.items():
        if lower.endswith(tuple(conf["exts"])):
            return media
    return None
