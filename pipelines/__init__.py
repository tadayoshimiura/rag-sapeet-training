"""パイプライン群（自作RAGから移植・共通化したもの）。"""

from pathlib import Path
import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)
__path__.append(str(Path(__file__).resolve().parent))
