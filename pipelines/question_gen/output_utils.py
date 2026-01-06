"""出力ファイルの書き込み補助（共通実装の参照）。"""

from shared.output_utils import (
    append_suffix,
    basename,
    is_s3_uri,
    split_s3_uri,
    write_json,
    write_text,
)
