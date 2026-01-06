#!/usr/bin/env python3
"""
S3バケットの versioning を前提に、Icon / .DS_Store を「完全削除」する。

注意:
- versioning有効だと、通常の delete では DeleteMarker が残ったり、
  変なキー（末尾に \\r が付くなど）が残ることがある。
- このスクリプトは対象キーの「全バージョン」と「DeleteMarker」を削除する。
"""

import argparse

import boto3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument(
        "--prefix",
        default="course_store/course_id=test_00/knowledge_md/v1/",
        help="対象プレフィックス（既定: course_store/.../knowledge_md/v1/）",
    )
    parser.add_argument("--dry-run", action="store_true", help="削除せず対象だけ表示する。")
    args = parser.parse_args()

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_object_versions")

    to_delete = []

    def _match(key: str) -> bool:
        name = key.split("/")[-1]
        return name.startswith("Icon") or name == ".DS_Store" or "/Icon" in key or "/.DS_Store" in key

    for page in paginator.paginate(Bucket=args.bucket, Prefix=args.prefix):
        for v in page.get("Versions", []):
            key = v["Key"]
            if not _match(key):
                continue
            to_delete.append({"Key": key, "VersionId": v["VersionId"]})
        for m in page.get("DeleteMarkers", []):
            key = m["Key"]
            if not _match(key):
                continue
            to_delete.append({"Key": key, "VersionId": m["VersionId"]})

    if not to_delete:
        print("対象なし")
        return

    for item in to_delete:
        print(f"delete: {item['Key']!r} (version={item['VersionId']})")
        if args.dry_run:
            continue
        s3.delete_object(Bucket=args.bucket, Key=item["Key"], VersionId=item["VersionId"])

    if args.dry_run:
        print("dry-run のため削除していません")
    else:
        print("削除完了")


if __name__ == "__main__":
    main()
