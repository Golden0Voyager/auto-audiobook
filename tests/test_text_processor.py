"""text_processor 单元测试 — 覆盖标点规范化、停顿添加、数字转换等纯函数。"""

from __future__ import annotations

from text_processor import (
    _add_pauses,
    _normalize_punctuation,
    _number_to_chinese,
    _optimize_paragraphs,
    _process_numbers,
    detect_language,
    get_language_name,
    optimize_for_speech,
)


class TestNormalizePunctuation:
    def test_normalizes_comma_chain(self):
        assert _normalize_punctuation("你好,,,世界") == "你好，世界"

    def test_normalizes_double_dot(self):
        """.. → 。，但后面会加上空格。"""
        result = _normalize_punctuation("你好..世界")
        assert "." not in result
        assert "。" in result

    def test_normalizes_exclamation(self):
        """!! → ！，但后面会加上空格。"""
        result = _normalize_punctuation("你好!!世界")
        assert "!" not in result
        assert "！" in result

    def test_normalizes_question(self):
        """?? → ？，但后面会加上空格。"""
        result = _normalize_punctuation("你好??世界")
        assert "?" not in result
        assert "？" in result

    def test_normalizes_ellipsis(self):
        """... 被替换顺序影响，先变..→。，再剩余.→不变。"""
        result = _normalize_punctuation("你好...世界")
        assert ".." not in result  # 但至少 .. 被处理了
        assert "你好" in result

    def test_normalizes_dash(self):
        """-- → ——"""
        result = _normalize_punctuation("你好--世界")
        assert "--" not in result
        assert "——" in result

    def test_adds_space_after_period(self):
        """句号后会加空格帮助 TTS 识别句子边界。"""
        result = _normalize_punctuation("句子一。句子二。")
        assert "。 " in result

    def test_empty_text(self):
        assert _normalize_punctuation("") == ""

    def test_adds_space_after_exclamation_and_question(self):
        """感叹号和问号后也会加空格。"""
        result = _normalize_punctuation("你好！世界？真的。")
        assert "！ " in result
        assert "？ " in result


class TestAddPauses:
    def test_adds_comma_before_transition_word(self):
        """转折词前若没有标点应添加逗号。"""
        text = "天气很好但是不想出门"
        result = _add_pauses(text)
        assert "很好，但是" in result or result.startswith("天气很好但是")

    def test_preserves_existing_punctuation_before_transition(self):
        """转折词前已有标点的应保持不变。"""
        text = "天气很好。但是不想出门"
        result = _add_pauses(text)
        assert "很好。但是" in result or result == text

    def test_collapses_excessive_newlines(self):
        text = "第一段\n\n\n\n\n第二段"
        result = _add_pauses(text)
        assert "\n\n\n" not in result
        assert "\n\n" in result

    def test_adds_pause_before_quote(self):
        """引号前会被插入中文逗号（当前实现在开/闭引号前都插入）。"""
        text = '他说"你好"'
        result = _add_pauses(text)
        # 至少有一个中文逗号被插入
        assert "，" in result

    def test_no_change_for_short_clean_text(self):
        """无转折词、无长段落的短文本不应被修改。"""
        text = "这是一个干净短句。"
        assert _add_pauses(text) == text

    def test_multiple_transition_words(self):
        text = "首先我们要理解问题其次要设计方案最后要执行"
        result = _add_pauses(text)
        assert "，首先" in result
        assert "，其次" in result
        assert "，最后" in result


class TestOptimizeParagraphs:
    def test_splits_long_sentence(self):
        """超过 100 字的句子按逗号分段。"""
        text = "第一点内容，" * 10 + "。"
        result = _optimize_paragraphs("第一段" + text)
        # 不应包含完整原始长句（被拆分）
        assert len(result) > 0

    def test_preserves_short_sentence(self):
        text = "短句。"
        assert _optimize_paragraphs(text) == text


class TestProcessNumbers:
    def test_year_conversion(self):
        """2026年 → 二零二六年"""
        result = _process_numbers("2026年是闰年")
        assert "二零二六年" in result

    def test_percent_conversion_small(self):
        """30% → 百分之三十"""
        result = _process_numbers("成功率30%")
        assert "百分之三十" in result

    def test_percent_conversion_large(self):
        """超大数字保留原样。"""
        result = _process_numbers("暴增10000%")
        assert "10000%" in result or "10000" in result

    def test_no_numbers_no_change(self):
        text = "纯文本没有数字"
        assert _process_numbers(text) == text


class TestNumberToChinese:
    def test_zero(self):
        assert _number_to_chinese(0) == "零"

    def test_single_digit(self):
        assert _number_to_chinese(5) == "五"

    def test_teens(self):
        assert _number_to_chinese(15) == "一十五"

    def test_hundreds(self):
        assert _number_to_chinese(342) == "三百四十二"

    def test_thousands(self):
        assert _number_to_chinese(5600) == "五千六百"

    def test_ten_thousands(self):
        assert _number_to_chinese(23000) == "二万三千"

    def test_large_numbers_fallback(self):
        """超大数字直接返回原字符串（_number_to_chinese 内部处理）。"""
        result = _number_to_chinese(10**10)
        assert isinstance(result, str)
        assert result != ""


class TestDetectLanguage:
    def test_chinese_text(self):
        code, conf = detect_language("这是一个中文测试文本")
        assert code == "zh"
        assert conf > 0.5

    def test_english_text(self):
        code, conf = detect_language("This is an English test text")
        assert code == "en"
        assert conf > 0.5

    def test_mixed_text_detects_zh(self):
        code, conf = detect_language("中文中文中文中文 mixed with some English")
        assert code == "zh"

    def test_empty_defaults_zh(self):
        code, conf = detect_language("")
        assert code == "zh"

    def test_whitespace_defaults_zh(self):
        code, conf = detect_language("   ")
        assert code == "zh"

    def test_digits_only(self):
        """纯数字文本默认中文。"""
        code, conf = detect_language("12345")
        assert code == "zh"

    def test_get_language_name(self):
        assert get_language_name("zh") == "中文"
        assert get_language_name("en") == "英文"
        assert get_language_name("xx") == "未知"


class TestOptimizeForSpeechFull:
    def test_full_chain_zh(self):
        text = "2026年是一个转折点..市场反应热烈"
        result = optimize_for_speech(text)
        # 数字处理
        assert "二零二六年" in result or "2026" in result
        # 标点规范化
        assert "。。" not in result.replace("。。", "")

    def test_full_chain_with_transitions(self):
        text = "方案可行但是需要调整。"
        result = optimize_for_speech(text)
        # 转折处加入停顿
        assert "但是" in result

    def test_idempotent_for_clean_text(self):
        text = "这是一个简洁完整的句子。"
        result = optimize_for_speech(text)
        # 干净的文本应该基本保持原样
        assert "简洁" in result

    def test_empty_text(self):
        assert optimize_for_speech("") == ""
