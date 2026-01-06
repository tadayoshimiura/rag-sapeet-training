"""
RAGコンポーネントの共通インターフェース例。

各クラウドごとにアダプタ実装を用意し、設定で差し替え可能にする前提の骨組み。
新しい構文は避け、シンプルなクラスとメソッドで構成しています。
"""


class StorageClient:
    """オブジェクトストレージの簡易クライアント。

    Args:
        bucket (str): 保存先のバケット名。

    Example:
        >>> client = StorageClient(bucket="my-bucket")
        >>> client.put("docs/id1.txt", b"hello")
    """

    def __init__(self, bucket):
        self.bucket = bucket

    def put(self, key, data):
        """バイナリデータを保存する。

        Args:
            key (str): オブジェクトキー。
            data (bytes): 保存するバイト列。
        """
        raise NotImplementedError

    def get(self, key):
        """バイナリデータを取得する。

        Args:
            key (str): オブジェクトキー。

        Returns:
            bytes: 取得したデータ。
        """
        raise NotImplementedError


class EmbeddingClient:
    """テキストをベクトル化するクライアント。

    Args:
        model (str): 使用する埋め込みモデル名。

    Example:
        >>> emb = EmbeddingClient(model="text-embedding-3-large")
        >>> vecs = emb.embed(["hello", "world"])
    """

    def __init__(self, model):
        self.model = model

    def embed(self, texts):
        """複数テキストを埋め込みベクトルに変換する。

        Args:
            texts (list[str]): テキストのリスト。

        Returns:
            list[list[float]]: ベクトルのリスト。
        """
        raise NotImplementedError


class VectorStoreClient:
    """ベクトルデータベースの簡易クライアント。

    Args:
        index_name (str): インデックス名。

    Example:
        >>> vs = VectorStoreClient(index_name="docs")
        >>> vs.upsert(ids=["id1"], vectors=[[0.1, 0.2]], meta=[{"title": "doc"}])
    """

    def __init__(self, index_name):
        self.index_name = index_name

    def upsert(self, ids, vectors, meta):
        """ベクトルとメタデータを登録する。

        Args:
            ids (list[str]): 一意のIDリスト。
            vectors (list[list[float]]): ベクトルのリスト。
            meta (list[dict]): メタデータのリスト。
        """
        raise NotImplementedError

    def query(self, vector, top_k):
        """ベクトル類似検索を行う。

        Args:
            vector (list[float]): クエリベクトル。
            top_k (int): 取得件数。

        Returns:
            list[dict]: スコアとメタデータを含む結果のリスト。
        """
        raise NotImplementedError


class Retriever:
    """レトリーバー: クエリを埋め込み、ベクトル検索する。

    Args:
        embedder (EmbeddingClient): 埋め込みクライアント。
        store (VectorStoreClient): ベクトルストアクライアント。

    Example:
        >>> retriever = Retriever(embedder, store)
        >>> hits = retriever.search("質問", top_k=5)
    """

    def __init__(self, embedder, store):
        self.embedder = embedder
        self.store = store

    def search(self, query, top_k=5):
        """テキストクエリで検索する。

        Args:
            query (str): 検索クエリ。
            top_k (int): 取得件数。

        Returns:
            list[dict]: 検索結果。
        """
        vectors = self.embedder.embed([query])
        return self.store.query(vectors[0], top_k=top_k)
