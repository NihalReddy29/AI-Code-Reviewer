from __future__ import annotations


def parse_tree(file_path: str, source_code: str) -> dict[str, str]:
    return {
        'file_path': file_path,
        'language': 'unknown',
        'source_length': str(len(source_code)),
    }
