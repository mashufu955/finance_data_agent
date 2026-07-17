import jieba.analyse
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.logging import logger

# ---- 金融领域自定义词典 ----
# 防止 jieba 将业务术语错误切分
_FINANCE_CUSTOM_WORDS = [
    "授信额度", "贷款余额", "逾期余额", "催收回收率",
    "风险等级", "理财产品", "贷款产品", "贷款合同",
    "还款计划", "逾期记录", "风控规则", "风险事件",
    "反洗钱", "人工复核", "催收案件", "黑名单",
    "新增客户", "活跃客户", "开户数", "交易金额",
    "交易笔数", "渠道交易", "账户余额", "冻结金额",
    "理财持仓", "持仓规模", "申购赎回", "理财规模",
    "贷款申请", "审批通过率", "放款金额", "合同状态",
    "还款金额", "提前还款", "费用减免", "逾期合同",
    "规则命中", "催收人员", "处置结果", "回收效果",
    "客户数", "用户数", "放款额", "AUM",
]

for _w in _FINANCE_CUSTOM_WORDS:
    jieba.add_word(_w)

# ---- 金融同义词映射 ----
# key: 口语化/别名表达 → value: 系统标准术语
# 用于在分词前对 query 做预处理，提升召回命中率
_FINANCE_SYNONYMS = {
    "用户数": "客户数",
    "用户量": "客户数",
    "客户量": "客户数",
    "AUM": "理财持仓规模",
    "理财规模": "理财持仓规模",
    "理财余额": "理财持仓规模",
    "放款额": "放款金额",
    "放款量": "放款金额",
    "逾期金额": "逾期余额",
    "逾期量": "逾期余额",
    "贷款量": "贷款余额",
    "贷款额": "贷款余额",
    "交易额": "交易金额",
    "交易量": "交易金额",
    "开户量": "开户数",
    "新增用户": "新增客户",
    "新增用户数": "新增客户数",
    "活跃用户": "活跃客户",
    "活跃用户数": "活跃客户数",
    "坏账": "逾期",
    "违约": "逾期",
    "欠款": "逾期",
    "存款余额": "账户余额",
    "存款": "账户余额",
}


def is_numeric(s: str) -> bool:
    """判断字符串是否为数值"""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _apply_synonyms(query: str) -> str:
    """将 query 中的口语化表达替换为标准术语"""
    result = query
    # 按长度降序排列，优先匹配更长的短语，避免子串误替换
    for alias, standard in sorted(_FINANCE_SYNONYMS.items(), key=lambda x: -len(x[0])):
        if alias in result:
            result = result.replace(alias, standard)
            logger.info(f"同义词替换: '{alias}' -> '{standard}'")
    return result


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """从查询中提取关键词，支持金融同义词标准化和自定义分词。"""
    writer = runtime.stream_writer
    writer({"stage": "抽取关键词"})

    query = state["query"]

    # 同义词预处理：将口语化表达替换为标准术语
    normalized_query = _apply_synonyms(query)

    # 对查询进行分词，只提取指定词性的词
    allow_pos = (
        "n",  # 名词: 数据、服务器、表格
        "nr",  # 人名: 张三、李四
        "ns",  # 地名: 北京、上海
        "nt",  # 机构团体名: 政府、学校、某公司
        "nz",  # 其他专有名词: Unicode、哈希算法、诺贝尔奖
        "v",  # 动词: 运行、开发
        "vn",  # 名动词: 工作、研究
        "a",  # 形容词: 美丽、快速
        "an",  # 名形词: 难度、合法性、复杂度
        "eng",  # 英文
        "i",  # 成语
        "l",  # 常用固定短语
    )

    # 同时从原始 query 和标准化后的 query 中提取关键词，取并集
    keywords = jieba.analyse.extract_tags(query, withWeight=False, allowPOS=allow_pos)
    keywords += jieba.analyse.extract_tags(normalized_query, withWeight=False, allowPOS=allow_pos)
    keywords = list(set(keywords + [query, normalized_query]))
    keywords = list(set([w for w in keywords if not is_numeric(w)]))

    # 将 classify_query 提取的 time_range 也加入关键词（如果有）
    time_range = state.get("time_range")
    if time_range:
        keywords.append(time_range)

    logger.info(f"关键词提取: {keywords}")
    return {"keywords": keywords}
