import logging
import re
from functools import lru_cache

import requests
_logger = logging.getLogger(__name__)

BASE_URL = "https://tinhthanhpho.com/api/v1"
CONFIG_PARAM_API_KEY = "ps_employee.tinhthanhpho_api_key"

_ABBREVIATIONS = [
    (r"(?<![a-z0-9])tp\.", "thành phố"),
    (r"(?<![a-z0-9])tx\.", "thị xã"),
    (r"(?<![a-z0-9])tt\.", "thị trấn"),
    (r"(?<![a-z0-9])q\.", "quận"),
    (r"(?<![a-z0-9])p\.", "phường"),
    (r"(?<![a-z0-9])h\.", "huyện"),
    (r"(?<![a-z0-9])x\.", "xã"),
    (r"(?<![a-z0-9])t\.", "tỉnh"),
]

def _expand_address(text):
    """Mở rộng các từ viết tắt phổ biến trong địa chỉ Việt Nam."""
    if not text:
        return ""
    for pattern, repl in _ABBREVIATIONS:
        text = re.sub(pattern, repl.capitalize(), text, flags=re.IGNORECASE)
    return text


def _normalize(text):
    if not text:
        return ""
    text = text.lower()
    for pattern, repl in _ABBREVIATIONS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text.strip())


def _get_api_key(env):
    return env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_API_KEY, "")


def _http_get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params or {}, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("data", []) if data.get("success") else []
    except requests.RequestException as exc:
        _logger.warning("VN address API GET failed (%s): %s", url, exc)
        return []


@lru_cache(maxsize=None)
def _get_provinces():
    return _http_get("/provinces", {"limit": 100})


@lru_cache(maxsize=None)
def _get_districts(province_code):
    if not province_code:
        return []
    return _http_get(f"/provinces/{province_code}/districts", {"limit": 1000})


@lru_cache(maxsize=None)
def _get_wards(district_code):
    if not district_code:
        return []
    return _http_get(f"/districts/{district_code}/wards", {"limit": 1000})


def _full_name(cand):
    name = cand.get("name", "")
    type_ = cand.get("type", "")
    if type_ and name:
        return f"{type_} {name}"
    return name


def _search_names(cand):
    """Trả về các biến thể tên để tìm kiếm: đầy đủ và rút gọn."""
    names = []
    full = _full_name(cand)
    norm_full = _normalize(full)
    if norm_full:
        names.append(norm_full)
    norm_name = _normalize(cand.get("name", ""))
    if norm_name and norm_name != norm_full:
        names.append(norm_name)
    return names


def _build_pattern(norm_name):
    """Regex khớp tên với ranh giới không phải chữ/số ASCII."""
    return re.compile(
        r"(?<![a-z0-9])" + re.escape(norm_name) + r"(?![a-z0-9])",
        flags=re.IGNORECASE,
    )


def _find_best_match(text, candidates):
    """Tìm candidate có tên xuất hiện ở vị trí phải nhất, ưu tiên tên dài hơn khi cùng vị trí."""
    if not text or not candidates:
        return None
    norm_text = _normalize(text)
    best = None
    best_pos = -1
    best_len = 0
    for cand in candidates:
        cand_pos = -1
        cand_len = 0
        for norm_name in _search_names(cand):
            pattern = _build_pattern(norm_name)
            for match in pattern.finditer(norm_text):
                pos = match.start()
                length = len(norm_name)
                if pos > cand_pos or (pos == cand_pos and length > cand_len):
                    cand_pos = pos
                    cand_len = length
        if cand_pos >= 0 and (
            cand_pos > best_pos or (cand_pos == best_pos and cand_len > best_len)
        ):
            best = cand
            best_pos = cand_pos
            best_len = cand_len
    return best


def _remove_candidate(text, cand):
    """Xóa duy nhất lần xuất hiện cuối cùng của tên candidate khỏi text.
    Ưu tiên tên đầy đủ (có loại) nếu cùng kết thúc ở vị trí cuối.
    """
    best_match = None
    best_len = -1
    best_end = -1
    for norm_name in _search_names(cand):
        pattern = _build_pattern(norm_name)
        for match in pattern.finditer(text):
            end = match.end()
            length = match.end() - match.start()
            if end > best_end or (end == best_end and length > best_len):
                best_end = end
                best_len = length
                best_match = match
    if not best_match:
        return text
    start, end = best_match.span()
    return text[:start] + " " * (end - start) + text[end:]


def _strip_admin_names(address, *candidates):
    """Loại bỏ các tên đơn vị hành chính đã nhận diện khỏi chuỗi địa chỉ."""
    result = address
    for cand in candidates:
        if not cand:
            continue
        result = _remove_candidate(result, cand)
    # Làm sạch dấu phẩy và khoảng trắng thừa
    result = re.sub(r"\s*,\s*", ", ", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip(" ,")


def parse_vn_address(address):
    """Tách chuỗi địa chỉ VN thành province/district/ward codes + street.
    Trả về dict hoặc None nếu không nhận diện được tỉnh/thành.
    """
    if not address or not address.strip():
        return None

    norm = _normalize(address)

    # Nhận diện tỉnh/thành phố
    province = _find_best_match(norm, _get_provinces())
    if not province:
        return None

    # Nhận diện quận/huyện, loại bỏ tên tỉnh để tránh nhầm
    text_without_province = _remove_candidate(norm, province)
    district = _find_best_match(text_without_province, _get_districts(province.get("code")))

    # Nhận diện phường/xã, loại bỏ tên quận/huyện khỏi text đã xóa tỉnh
    text_without_district = text_without_province
    ward = None
    if district:
        text_without_district = _remove_candidate(text_without_district, district)
        ward = _find_best_match(text_without_district, _get_wards(district.get("code")))

    # Tách địa chỉ đường phố
    street = _strip_admin_names(_expand_address(address), province, district, ward)

    return {
        "province_code": province.get("code"),
        "district_code": district.get("code") if district else None,
        "ward_code": ward.get("code") if ward else None,
        "province_name": province.get("name"),
        "district_name": district.get("name") if district else None,
        "ward_name": ward.get("name") if ward else None,
        "street": street,
    }


def convert_old_to_new_address(province_code, district_code, ward_code, street_address, api_key):
    """Gọi API convert để lấy địa chỉ mới.
    Trả về dict {'old': ..., 'new': ..., 'mergeInfo': ...} hoặc None.
    """
    if not api_key or not (province_code and district_code and ward_code):
        return None

    url = f"{BASE_URL}/convert/address"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "provinceCode": province_code,
                "districtCode": district_code,
                "wardCode": ward_code,
                "streetAddress": street_address or "",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data") if data.get("success") else None
    except requests.RequestException as exc:
        _logger.warning("VN address API POST failed (%s): %s", url, exc)
        return None


def _find_vn_country(env):
    return env["res.country"].search([("code", "=", "VN")], limit=1)


def _find_state(env, province_name):
    """Tìm res.country.state của Việt Nam khớp với tên tỉnh/thành phố."""
    if not province_name:
        return env["res.country.state"].browse()
    country = _find_vn_country(env)
    if not country:
        return env["res.country.state"].browse()

    norm = _normalize(province_name)
    states = env["res.country.state"].search([("country_id", "=", country.id)])

    partial_match = None
    for state in states:
        state_norm = _normalize(state.name)
        if state_norm == norm:
            return state
        if not partial_match and (norm in state_norm or state_norm in norm):
            partial_match = state
    return partial_match or env["res.country.state"].browse()
