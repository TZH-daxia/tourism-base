import hashlib
import os
import re
from typing import Iterable


DOC_TYPE_KEYWORDS = {
    "交通指南": "交通指南",
    "景点攻略": "景点攻略",
    "景点推荐": "景点攻略",
    "酒店信息": "酒店信息",
    "美食推荐": "美食推荐",
    "线路推荐": "线路推荐",
}

OVERVIEW_DOC_TYPES = ["景点攻略", "线路推荐", "美食推荐", "酒店信息", "交通指南"]


def infer_city_from_filename(file_name: str) -> str:
    stem = os.path.splitext(os.path.basename(file_name))[0]
    stem = re.sub(r"^[0-9A-Za-z_\-\s]+", "", stem)
    for keyword in DOC_TYPE_KEYWORDS:
        stem = stem.replace(keyword, "")
    stem = _normalize_city_name(stem)
    match = re.match(r"^([\u4e00-\u9fff]{2,4})", stem)
    return match.group(1) if match else stem[:4]


def infer_city(file_name: str, content: str = "") -> str:
    city = infer_city_from_filename(file_name)
    if city and re.search(r"[\u4e00-\u9fff]", city):
        return _normalize_city_name(city)
    match = re.search(r"城市[:：]\s*([\u4e00-\u9fff]{2,4})", content or "")
    if match:
        return _normalize_city_name(match.group(1))
    match = re.search(r"#\s*([\u4e00-\u9fff]{2,4})", content or "")
    if match:
        return _normalize_city_name(match.group(1))
    return _normalize_city_name(city)


def _normalize_city_name(city: str) -> str:
    city = normalize_text(city)
    changed = True
    while changed and city:
        changed = False
        for suffix in ("交通指南", "景点攻略", "景点推荐", "酒店信息", "住宿推荐", "美食推荐", "线路推荐", "交通", "景点", "酒店", "住宿", "美食", "线路", "旅游", "攻略", "推荐"):
            if city.endswith(suffix) and len(city) > len(suffix) + 1:
                city = city[: -len(suffix)]
                changed = True
                break
    return city


def is_valid_city_name(city: str) -> bool:
    normalized = _normalize_city_name(city)
    if not normalized:
        return False
    if len(normalized) < 2 or len(normalized) > 8:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]+", normalized):
        return False
    invalid_tokens = {"未知", "其他", "资料", "文档", "图片"}
    return normalized not in invalid_tokens


def infer_doc_type(file_name: str, content: str = "") -> str:
    text = f"{file_name}\n{content[:200]}".strip()
    for keyword, normalized in DOC_TYPE_KEYWORDS.items():
        if keyword in text:
            return normalized
    return "旅游资料"


def build_product_id(city: str) -> str:
    safe_city = normalize_text(city) or "unknown"
    return f"city::{safe_city}"


def build_chunk_id(product_id: str, source_file: str, chunk_index: int) -> str:
    digest = hashlib.md5(f"{product_id}:{source_file}:{chunk_index}".encode("utf-8")).hexdigest()[:12]
    return f"{product_id}::{chunk_index:04d}::{digest}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def build_suggested_queries(city: str, available_doc_types: Iterable[str] | None = None) -> list[str]:
    doc_types = set(available_doc_types or [])
    options = [
        f"{city}有什么好玩的？",
        f"{city}住哪里方便，吃什么值得推荐？",
        f"{city}怎么安排行程和交通更省心？",
    ]
    if "线路推荐" in doc_types:
        options[2] = f"{city}有哪些值得参考的旅游线路？"
    return options[:3]


def detect_need_images(query: str) -> bool:
    keywords = ("图片", "照片", "看看", "长什么样", "景色", "实拍", "图")
    return any(keyword in (query or "") for keyword in keywords)


def extract_image_markdown(content: str) -> list[dict]:
    results = []
    for alt, url in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content or ""):
        results.append({"alt": alt.strip() or "旅游图片", "url": url.strip()})
    return results
