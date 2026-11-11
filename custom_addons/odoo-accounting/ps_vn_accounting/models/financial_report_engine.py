# -*- coding: utf-8 -*-
"""Engine đánh giá công thức báo cáo tài chính TT99."""

import logging
import re
from datetime import timedelta


_logger = logging.getLogger(__name__)

# Tên chỉ tiêu cho Bảng cân đối kế toán TT99 (BCDKT)
TT99_BCDKT_LABELS = {
    "@1004": "A. TÀI SẢN NGẮN HẠN",
    "@1005": "A. TÀI SẢN NGẮN HẠN",
    "@1104": "I. Tiền và các khoản tương đương tiền",
    "@1105": "I. Tiền và các khoản tương đương tiền",
    "@1114": "1. Tiền",
    "@1115": "1. Tiền",
    "@1124": "2. Các khoản tương đương tiền",
    "@1125": "2. Các khoản tương đương tiền",
    "@1204": "II. Các khoản đầu tư tài chính ngắn hạn",
    "@1205": "II. Các khoản đầu tư tài chính ngắn hạn",
    "@1214": "1. Chứng khoán kinh doanh",
    "@1215": "1. Chứng khoán kinh doanh",
    "@1224": "2. Dự phòng giảm giá chứng khoán kinh doanh (*)",
    "@1225": "2. Dự phòng giảm giá chứng khoán kinh doanh (*)",
    "@1234": "3. Đầu tư nắm giữ đến ngày đáo hạn",
    "@1235": "3. Đầu tư nắm giữ đến ngày đáo hạn",
    "@1304": "III. Các khoản phải thu ngắn hạn",
    "@1305": "III. Các khoản phải thu ngắn hạn",
    "@1314": "1. Phải thu ngắn hạn của khách hàng",
    "@1315": "1. Phải thu ngắn hạn của khách hàng",
    "@1324": "2. Trả trước cho người bán ngắn hạn",
    "@1325": "2. Trả trước cho người bán ngắn hạn",
    "@1334": "3. Phải thu nội bộ ngắn hạn",
    "@1335": "3. Phải thu nội bộ ngắn hạn",
    "@1344": "4. Phải thu theo tiến độ kế hoạch hợp đồng xây dựng",
    "@1345": "4. Phải thu theo tiến độ kế hoạch hợp đồng xây dựng",
    "@1354": "5. Phải thu về cho vay ngắn hạn",
    "@1355": "5. Phải thu về cho vay ngắn hạn",
    "@1364": "6. Phải thu ngắn hạn khác",
    "@1365": "6. Phải thu ngắn hạn khác",
    "@1374": "7. Dự phòng phải thu ngắn hạn khó đòi (*)",
    "@1375": "7. Dự phòng phải thu ngắn hạn khó đòi (*)",
    "@1394": "8. Tài sản thiếu chờ xử lý",
    "@1395": "8. Tài sản thiếu chờ xử lý",
    "@1404": "IV. Hàng tồn kho",
    "@1405": "IV. Hàng tồn kho",
    "@1414": "1. Hàng tồn kho",
    "@1415": "1. Hàng tồn kho",
    "@1494": "2. Dự phòng giảm giá hàng tồn kho (*)",
    "@1495": "2. Dự phòng giảm giá hàng tồn kho (*)",
    "@1504": "V. Tài sản ngắn hạn khác",
    "@1505": "V. Tài sản ngắn hạn khác",
    "@1514": "1. Chi phí trả trước ngắn hạn",
    "@1515": "1. Chi phí trả trước ngắn hạn",
    "@1524": "2. Thuế GTGT được khấu trừ",
    "@1525": "2. Thuế GTGT được khấu trừ",
    "@1534": "3. Thuế và các khoản khác phải thu Nhà nước",
    "@1535": "3. Thuế và các khoản khác phải thu Nhà nước",
    "@1544": "4. Giao dịch mua bán nợ tài chính",
    "@1545": "4. Giao dịch mua bán nợ tài chính",
    "@1554": "5. Tài sản ngắn hạn khác",
    "@1555": "5. Tài sản ngắn hạn khác",
    "@2004": "B. TÀI SẢN DÀI HẠN",
    "@2005": "B. TÀI SẢN DÀI HẠN",
    "@2104": "I. Các khoản phải thu dài hạn",
    "@2105": "I. Các khoản phải thu dài hạn",
    "@2114": "1. Phải thu dài hạn của khách hàng",
    "@2115": "1. Phải thu dài hạn của khách hàng",
    "@2124": "2. Trả trước cho người bán dài hạn",
    "@2125": "2. Trả trước cho người bán dài hạn",
    "@2134": "3. Phải thu về cho vay dài hạn",
    "@2135": "3. Phải thu về cho vay dài hạn",
    "@2144": "4. Phải thu dài hạn nội bộ",
    "@2145": "4. Phải thu dài hạn nội bộ",
    "@2154": "5. Phải thu về vốn kinh doanh ở đơn vị trực thuộc",
    "@2155": "5. Phải thu về vốn kinh doanh ở đơn vị trực thuộc",
    "@2164": "6. Phải thu dài hạn khác",
    "@2165": "6. Phải thu dài hạn khác",
    "@2194": "7. Dự phòng phải thu dài hạn khó đòi (*)",
    "@2195": "7. Dự phòng phải thu dài hạn khó đòi (*)",
    "@2204": "II. Tài sản cố định",
    "@2205": "II. Tài sản cố định",
    "@2214": "1. Tài sản cố định hữu hình",
    "@2215": "1. Tài sản cố định hữu hình",
    "@2224": "- Nguyên giá",
    "@2225": "- Nguyên giá",
    "@2234": "- Giá trị hao mòn luỹ kế",
    "@2235": "- Giá trị hao mòn luỹ kế",
    "@2244": "2. Tài sản cố định thuê tài chính",
    "@2245": "2. Tài sản cố định thuê tài chính",
    "@2254": "- Nguyên giá",
    "@2255": "- Nguyên giá",
    "@2264": "- Giá trị hao mòn luỹ kế",
    "@2265": "- Giá trị hao mòn luỹ kế",
    "@2274": "3. Tài sản cố định vô hình",
    "@2275": "3. Tài sản cố định vô hình",
    "@2284": "- Nguyên giá",
    "@2285": "- Nguyên giá",
    "@2294": "- Giá trị hao mòn luỹ kế",
    "@2295": "- Giá trị hao mòn luỹ kế",
    "@2304": "III. Bất động sản đầu tư",
    "@2305": "III. Bất động sản đầu tư",
    "@2314": "- Nguyên giá",
    "@2315": "- Nguyên giá",
    "@2324": "- Giá trị hao mòn luỹ kế",
    "@2325": "- Giá trị hao mòn luỹ kế",
    "@2404": "IV. Các khoản đầu tư tài chính dài hạn",
    "@2405": "IV. Các khoản đầu tư tài chính dài hạn",
    "@2414": "1. Đầu tư vào công ty liên kết",
    "@2415": "1. Đầu tư vào công ty liên kết",
    "@2424": "2. Đầu tư dài hạn khác",
    "@2425": "2. Đầu tư dài hạn khác",
    "@2434": "3. Dự phòng giảm giá đầu tư tài chính dài hạn (*)",
    "@2435": "3. Dự phòng giảm giá đầu tư tài chính dài hạn (*)",
    "@2504": "V. Tài sản dài hạn khác",
    "@2505": "V. Tài sản dài hạn khác",
    "@2514": "1. Chi phí trả trước dài hạn",
    "@2515": "1. Chi phí trả trước dài hạn",
    "@2524": "2. Tài sản thuế thu nhập hoãn lại",
    "@2525": "2. Tài sản thuế thu nhập hoãn lại",
    "@2534": "3. Thiệt hại tài sản dài hạn chờ xử lý",
    "@2535": "3. Thiệt hại tài sản dài hạn chờ xử lý",
    "@2544": "4. Lợi thế thương mại",
    "@2545": "4. Lợi thế thương mại",
    "@2554": "5. Tài sản dài hạn khác",
    "@2555": "5. Tài sản dài hạn khác",
    "@2604": "VI. Xây dựng cơ bản dở dang",
    "@2605": "VI. Xây dựng cơ bản dở dang",
    "@2614": "1. Chi phí xây dựng cơ bản dở dang",
    "@2615": "1. Chi phí xây dựng cơ bản dở dang",
    "@2624": "2. Chi phí sửa chữa tài sản cố định lớn dở dang",
    "@2625": "2. Chi phí sửa chữa tài sản cố định lớn dở dang",
    "@2634": "3. Tài sản cố định đang chờ thanh lý",
    "@2635": "3. Tài sản cố định đang chờ thanh lý",
    "@2704": "TỔNG CỘNG TÀI SẢN",
    "@2705": "TỔNG CỘNG TÀI SẢN",
    "@3004": "C. NỢ PHẢI TRẢ",
    "@3005": "C. NỢ PHẢI TRẢ",
    "@3104": "I. Nợ phải trả ngắn hạn",
    "@3105": "I. Nợ phải trả ngắn hạn",
    "@3114": "1. Phải trả người bán ngắn hạn",
    "@3115": "1. Phải trả người bán ngắn hạn",
    "@3124": "2. Ngưởi mua trả tiền trước ngắn hạn",
    "@3125": "2. Ngưởi mua trả tiền trước ngắn hạn",
    "@3134": "3. Thuế và các khoản phải nộp Nhà nước",
    "@3135": "3. Thuế và các khoản phải nộp Nhà nước",
    "@3144": "4. Phải trả người lao động",
    "@3145": "4. Phải trả người lao động",
    "@3154": "5. Chi phí phải trả ngắn hạn",
    "@3155": "5. Chi phí phải trả ngắn hạn",
    "@3164": "6. Phải trả nội bộ ngắn hạn",
    "@3165": "6. Phải trả nội bộ ngắn hạn",
    "@3174": "7. Doanh thu chưa thực hiện ngắn hạn",
    "@3175": "7. Doanh thu chưa thực hiện ngắn hạn",
    "@3184": "8. Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "@3185": "8. Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "@3194": "9. Phải trả ngắn hạn khác",
    "@3195": "9. Phải trả ngắn hạn khác",
    "@3204": "10. Doanh thu chưa thực hiện dài hạn",
    "@3205": "10. Doanh thu chưa thực hiện dài hạn",
    "@3214": "11. Phải trả dài hạn khác",
    "@3215": "11. Phải trả dài hạn khác",
    "@3224": "12. Quỹ khen thưởng, phúc lợi",
    "@3225": "12. Quỹ khen thưởng, phúc lợi",
    "@3234": "13. Quỹ bình ổn giá",
    "@3235": "13. Quỹ bình ổn giá",
    "@3244": "14. Giao dịch mua bán nợ tài chính",
    "@3245": "14. Giao dịch mua bán nợ tài chính",
    "@3304": "II. Nợ phải trả dài hạn",
    "@3305": "II. Nợ phải trả dài hạn",
    "@3314": "1. Phải trả người bán dài hạn",
    "@3315": "1. Phải trả người bán dài hạn",
    "@3324": "2. Ngưởi mua trả tiền trước dài hạn",
    "@3325": "2. Ngưởi mua trả tiền trước dài hạn",
    "@3334": "3. Chi phí phải trả dài hạn",
    "@3335": "3. Chi phí phải trả dài hạn",
    "@3344": "4. Phải trả nội bộ dài hạn",
    "@3345": "4. Phải trả nội bộ dài hạn",
    "@3354": "5. Doanh thu chưa thực hiện dài hạn",
    "@3355": "5. Doanh thu chưa thực hiện dài hạn",
    "@3364": "6. Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "@3365": "6. Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "@3374": "7. Phải trả dài hạn khác",
    "@3375": "7. Phải trả dài hạn khác",
    "@3384": "8. Thuế thu nhập hoãn lại phải trả",
    "@3385": "8. Thuế thu nhập hoãn lại phải trả",
    "@3394": "9. Doanh thu chưa thực hiện dài hạn",
    "@3395": "9. Doanh thu chưa thực hiện dài hạn",
    "@3404": "10. Trái phiếu phát hành",
    "@3405": "10. Trái phiếu phát hành",
    "@3414": "11. Chi phí xây dựng cơ bản dở dang dài hạn",
    "@3415": "11. Chi phí xây dựng cơ bản dở dang dài hạn",
    "@3424": "12. Quỹ khen thưởng, phúc lợi dài hạn",
    "@3425": "12. Quỹ khen thưởng, phúc lợi dài hạn",
    "@3434": "13. Quỹ phát triển khoa học và công nghệ",
    "@3435": "13. Quỹ phát triển khoa học và công nghệ",
    "@4004": "D. VỐN CHỦ SỞ HỮU",
    "@4005": "D. VỐN CHỦ SỞ HỮU",
    "@4104": "I. Vốn chủ sở hữu",
    "@4105": "I. Vốn chủ sở hữu",
    "@4114": "1. Vốn góp của chủ sở hữu",
    "@4115": "1. Vốn góp của chủ sở hữu",
    "@4114a": "- Vốn nhà nước đầu tư",
    "@4115a": "- Vốn nhà nước đầu tư",
    "@4124": "2. Thặng dư vốn cổ phần",
    "@4125": "2. Thặng dư vốn cổ phần",
    "@4134": "3. Quyền chọn chuyển đổi trái phiếu",
    "@4135": "3. Quyền chọn chuyển đổi trái phiếu",
    "@4134b": "- Vốn khác của chủ sở hữu",
    "@4135b": "- Vốn khác của chủ sở hữu",
    "@4144": "4. Cổ phiếu quỹ",
    "@4145": "4. Cổ phiếu quỹ",
    "@4154": "5. Chênh lệch đánh giá lại tài sản",
    "@4155": "5. Chênh lệch đánh giá lại tài sản",
    "@4164": "6. Chênh lệch tỷ giá hối đoái",
    "@4165": "6. Chênh lệch tỷ giá hối đoái",
    "@4174": "7. Quỹ đầu tư phát triển",
    "@4175": "7. Quỹ đầu tư phát triển",
    "@4184": "8. Quỹ hỗ trợ sắp xếp doanh nghiệp",
    "@4185": "8. Quỹ hỗ trợ sắp xếp doanh nghiệp",
    "@4194": "9. Các quỹ khác thuộc vốn chủ sở hữu",
    "@4195": "9. Các quỹ khác thuộc vốn chủ sở hữu",
    "@4204": "II. Nguồn kinh phí và quỹ khác",
    "@4205": "II. Nguồn kinh phí và quỹ khác",
    "@4214": "1. Lợi nhuận sau thuế chưa phân phối",
    "@4215": "1. Lợi nhuận sau thuế chưa phân phối",
    "@4214a": "- LNST chưa phân phối năm nay",
    "@4215a": "- LNST chưa phân phối năm nay",
    "@4214b": "- LNST chưa phân phối năm trước",
    "@4215b": "- LNST chưa phân phối năm trước",
    "@4224": "2. Nguồn kinh phí",
    "@4225": "2. Nguồn kinh phí",
    "@4304": "III. Lợi ích cổ đông không kiểm soát",
    "@4305": "III. Lợi ích cổ đông không kiểm soát",
    "@4314": "1. Lợi ích của cổ đông không kiểm soát",
    "@4315": "1. Lợi ích của cổ đông không kiểm soát",
    "@4324": "2. Lợi nhuận hoặc lỗ chưa thực hiện",
    "@4325": "2. Lợi nhuận hoặc lỗ chưa thực hiện",
    "@4404": "TỔNG CỘNG NGUỒN VỐN",
    "@4405": "TỔNG CỘNG NGUỒN VỐN",
}


class FinancialReportEngine:
    """Engine đánh giá công thức báo cáo tài chính."""

    def __init__(self, env, company_id, date_from, date_to):
        self.env = env
        self.company_id = company_id
        self.date_from = date_from
        self.date_to = date_to
        self._cache = {}

    def evaluate_template(self, template):
        """Đánh giá toàn bộ công thức của một mẫu báo cáo."""
        lines = []
        formulas = template.x_formula_ids.sorted("x_sequence")

        # Tính toán lần lượt theo sequence
        for formula in formulas:
            seq = formula.x_sequence
            if seq not in self._cache:
                self._cache[seq] = {}

            label = formula.x_label or TT99_BCDKT_LABELS.get(formula.x_code, formula.x_code)
            level = formula.x_level if formula.x_label else self._infer_level(formula.x_code)
            line_type = formula.x_line_type if formula.x_label else self._infer_line_type(formula.x_code)

            if formula.x_formula:
                try:
                    ck_value = self._eval_formula(formula.x_formula, period="CK")
                    dk_value = self._eval_formula(formula.x_formula, period="DK")
                except Exception as e:  # noqa: BLE001
                    ck_value = 0.0
                    dk_value = 0.0
                    _logger.warning("Error evaluating %s: %s", formula.x_code, e)
            else:
                ck_value = 0.0
                dk_value = 0.0

            self._cache[seq]["CK"] = ck_value
            self._cache[seq]["DK"] = dk_value

            lines.append({
                "sequence": seq,
                "code": formula.x_code,
                "label": label,
                "level": level,
                "line_type": line_type,
                "value_ck": ck_value,
                "value_dk": dk_value,
            })

        return lines

    def _infer_level(self, code):
        """Xác định cấp độ thụt lề từ mã công thức."""
        base = code.replace("@", "").replace("4", "").replace("5", "")
        # Bỏ suffix a, b
        base = base.rstrip("ab")
        if base in ("100", "200", "300", "400", "270", "440"):
            return 0
        if base in ("110", "120", "130", "140", "150",
                    "210", "220", "230", "240", "250", "260",
                    "310", "330", "410", "430"):
            return 1
        return 2

    def _infer_line_type(self, code):
        """Xác định loại dòng từ mã công thức."""
        base = code.replace("@", "").replace("4", "").replace("5", "")
        base = base.rstrip("ab")
        if base in ("100", "200", "300", "400", "270", "440"):
            return "total"
        if base in ("110", "120", "130", "140", "150",
                    "210", "220", "230", "240", "250", "260",
                    "310", "330", "410", "430"):
            return "group"
        return "detail"

    def _eval_formula(self, formula, period):
        """Đánh giá một công thức với kỳ cho trước."""
        if not formula:
            return 0.0

        expr = formula.strip()

        # Thay @rptid bằng company_id (không thực sự dùng trong tính toán)
        expr = expr.replace("@rptid", str(self.company_id))

        # Xử lý các hàm SC, AR, AP
        expr = self._replace_functions(expr, "SC", self._eval_sc, period)
        expr = self._replace_functions(expr, "AR", self._eval_ar, period)
        expr = self._replace_functions(expr, "AP", self._eval_ap, period)
        expr = self._replace_functions(expr, "PS", self._eval_ps, period)

        # Xử lý hàm CONG
        expr = self._replace_cong(expr, period)

        # Đánh giá biểu thức số học còn lại
        try:
            result = eval(expr, {"__builtins__": {}}, {})
        except Exception:
            result = 0.0
        return float(result)

    def _replace_functions(self, expr, func_name, handler, period):
        """Thay thế các lời gọi hàm bằng giá trị số."""
        pattern = re.compile(rf"{func_name}\(([^)]+)\)")

        def repl(match):
            args = [a.strip().strip("'\"") for a in match.group(1).split(",")]
            return str(handler(args, period))

        return pattern.sub(repl, expr)

    def _eval_sc(self, args, period):
        """Đánh giá hàm SC(account, side, condition, period)."""
        account = args[1] if len(args) > 1 else ""
        side = args[2] if len(args) > 2 else "N"
        date = self.date_to if period == "CK" else self._opening_date()
        balance = self._get_account_balance(account, date)
        return self._side_balance(balance, side)

    def _eval_ar(self, args, period):
        """Đánh giá hàm AR(account, side, period)."""
        account = args[1] if len(args) > 1 else ""
        side = args[2] if len(args) > 2 else "N"
        date = self.date_to if period == "CK" else self._opening_date()
        balance = self._get_account_balance(account, date)
        return self._side_balance(balance, side)

    def _eval_ap(self, args, period):
        """Đánh giá hàm AP(account, side, period)."""
        account = args[1] if len(args) > 1 else ""
        side = args[2] if len(args) > 2 else "C"
        date = self.date_to if period == "CK" else self._opening_date()
        balance = self._get_account_balance(account, date)
        return self._side_balance(balance, side)

    def _eval_ps(self, args, period):
        """Đánh giá hàm PS(contra_account, account, condition, period).

        Hàm này tính phát sinh trong kỳ. Với báo cáo BCDKT thường không dùng,
        nên trả về 0 nếu chưa cần thiết.
        """
        # TODO: implement nếu cần cho KQKD/LCTT
        return 0.0

    def _replace_cong(self, expr, period):
        """Thay thế CONG('seq1'+'seq2'...) bằng tổng giá trị các sequence."""
        pattern = re.compile(r"CONG\(([^)]+)\)")

        def repl(match):
            inner = match.group(1)
            # Giữ dấu + hoặc - trước mỗi số; hỗ trợ cả chuỗi malformed như '93+'95'
            tokens = re.findall(r"([+-]?)\s*'?(\d+)'?", inner)
            total = 0.0
            for sign, seq_str in tokens:
                seq = int(seq_str)
                val = self._cache.get(seq, {}).get(period, 0.0)
                if sign == "-":
                    total -= val
                else:
                    total += val
            return str(total)

        return pattern.sub(repl, expr)

    def _get_account_balance(self, account_code, date):
        """Tính số dư Nợ - Có của tài khoản đến một ngày nhất định."""
        if not account_code:
            return 0.0
        domain = [
            ("account_id.code", "=like", account_code + "%"),
            ("date", "<=", date),
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.company_id),
        ]
        result = self.env["account.move.line"]._read_group(
            domain,
            aggregates=["debit:sum", "credit:sum"],
        )
        if not result:
            return 0.0
        debit = result[0][0] or 0.0
        credit = result[0][1] or 0.0
        return debit - credit

    def _opening_date(self):
        """Ngày để tính số dư đầu kỳ (ngày trước date_from)."""
        return self.date_from - timedelta(days=1)

    def _side_balance(self, balance, side):
        """Trả về số dư theo bên Nợ/Có."""
        if side == "N":
            return balance if balance > 0 else 0.0
        if side == "C":
            return -balance if balance < 0 else 0.0
        return balance
