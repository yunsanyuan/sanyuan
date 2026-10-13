from decimal import Decimal

SHOP_NAME = "花间集"
SLOGAN = "以花为集，以客为心"

LEVEL_STYLE = {
    "normal": "lv-normal",
    "silver": "lv-silver",
    "gold": "lv-gold",
    "diamond": "lv-diamond",
}

LEVEL_MARKS = {
    "normal": "○",
    "silver": "◇",
    "gold": "★",
    "diamond": "◆",
}

LEVEL_TAGLINES = {
    "normal": "从一束花开始",
    "silver": "银辉初绽",
    "gold": "金辉礼遇",
    "diamond": "花间最高礼遇",
}

LEVEL_EXTRAS = {
    "normal": ("可领取店铺优惠券", "开通积分与储值账户"),
    "silver": ("花市显示银卡价", "积分加速升级"),
    "gold": ("花市显示金卡价", "节日花礼优先备货"),
    "diamond": ("绿金专属界面与徽记", "优先预订与专属包装建议"),
}


def display_name(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return "访客"
    profile = getattr(user, "member_profile", None)
    if profile and profile.real_name:
        return profile.real_name
    return user.get_username()


def zhe_label(rate) -> str:
    rate = Decimal(str(rate))
    if rate >= Decimal("1.00"):
        return "原价"
    return f"{int(rate * 100)}折"


def level_perk(level) -> str:
    if level is None:
        return "注册即享积分累计"
    if level.discount_rate >= Decimal("1.00"):
        return f"积分起步 · {level.points_multiplier} 倍积分"
    return f"全场 {zhe_label(level.discount_rate)} · {level.points_multiplier} 倍积分"


def privilege_lines(level) -> list[str]:
    if level is None:
        return ["注册即享积分累计"]
    lines = []
    if level.discount_rate >= Decimal("1.00"):
        lines.append("原价选花，积分按消费累计")
    else:
        lines.append(f"全场 {zhe_label(level.discount_rate)}")
    lines.append(f"{level.points_multiplier} 倍积分")
    lines.extend(LEVEL_EXTRAS.get(level.code, ()))
    return lines


def level_snapshot(level) -> dict:
    code = getattr(level, "code", "normal") if level else "normal"
    name = getattr(level, "name", "普通") if level else "普通"
    return {
        "code": code,
        "name": name,
        "min_points": getattr(level, "min_points", 0) if level else 0,
        "discount_rate": getattr(level, "discount_rate", Decimal("1.00")) if level else Decimal("1.00"),
        "points_multiplier": getattr(level, "points_multiplier", Decimal("1.00")) if level else Decimal("1.00"),
        "zhe": zhe_label(level.discount_rate) if level else "原价",
        "perk": level_perk(level),
        "badge_class": LEVEL_STYLE.get(code, "lv-normal"),
        "mark": LEVEL_MARKS.get(code, "○"),
        "tagline": LEVEL_TAGLINES.get(code, "从一束花开始"),
        "privileges": privilege_lines(level),
    }


def level_catalog() -> list[dict]:
    from apps.members.models import MemberLevel

    return [level_snapshot(level) for level in MemberLevel.objects.order_by("sort_order", "min_points")]


def level_progress(member) -> dict:
    if member is None or member.level_id is None:
        return {"is_top": False, "percent": 0, "need_points": 0, "next_name": "", "perk": ""}
    current = member.level
    nxt = current.__class__.objects.filter(min_points__gt=current.min_points).order_by("min_points").first()
    if nxt is None:
        return {
            "is_top": True,
            "percent": 100,
            "need_points": 0,
            "next_name": "",
            "perk": level_perk(current),
        }
    span = max(1, nxt.min_points - current.min_points)
    done = max(0, member.total_points - current.min_points)
    need = max(0, nxt.min_points - member.total_points)
    return {
        "is_top": False,
        "percent": min(100, int(done * 100 / span)),
        "need_points": need,
        "next_name": f"{nxt.name}会员",
        "perk": level_perk(nxt),
    }


def welcome_payload(user=None, with_progress: bool = False) -> dict:
    empty = {
        "title": SLOGAN,
        "home_title": SLOGAN,
        "text": "注册会员，积分升级，把喜欢的花带回家。",
        "role": "guest",
        "level_code": "",
        "level_name": "",
        "badge_class": "lv-guest",
        "perk": "普通会员起步，银卡 98 折，金卡 95 折，钻石 92 折",
        "progress": None,
    }
    if not user or not getattr(user, "is_authenticated", False):
        return empty

    name = display_name(user)
    role = getattr(user, "role", "")
    if role == "admin":
        return {
            "title": f"管理员 {name}，欢迎回到{SHOP_NAME}",
            "home_title": f"欢迎回来，{name}",
            "text": f"{SLOGAN}。店务、会员与花市都在您手中，今日也把花事打理妥帖。",
            "role": "admin",
            "level_code": "admin",
            "level_name": "管理员",
            "badge_class": "lv-admin",
            "perk": "全店经营与退款权限",
            "progress": None,
        }
    if role == "staff":
        return {
            "title": f"店员 {name}，欢迎回到{SHOP_NAME}",
            "home_title": f"欢迎回来，{name}",
            "text": f"{SLOGAN}。收银、备花、发券，把好花送到客人心上。",
            "role": "staff",
            "level_code": "staff",
            "level_name": "店员",
            "badge_class": "lv-staff",
            "perk": "商品、订单收银与优惠券发放",
            "progress": None,
        }

    profile = getattr(user, "member_profile", None)
    level = getattr(profile, "level", None) if profile else None
    code = getattr(level, "code", "normal") if level else "normal"
    level_name = f"{level.name}会员" if level else "普通会员"
    progress = level_progress(profile) if with_progress and profile else None
    perk = level_perk(level)
    texts = {
        "normal": f"{name}，欢迎来到{SHOP_NAME}。你已是普通会员，消费累计积分，升至银卡即可全场 98 折。",
        "silver": f"银卡会员 {name}，欢迎回来。98 折与 1.1 倍积分已生效，再攒积分可升金卡，尊享 95 折。",
        "gold": f"金卡会员 {name}，{SHOP_NAME}候您多时。95 折礼遇已备好，距钻石只差一步，钻石可享 92 折与 1.5 倍积分。",
        "diamond": f"钻石会员 {name}，最高礼遇已为您打开：全场 92 折、1.5 倍积分，把心仪的花带回家。",
    }
    titles = {
        "normal": f"普通会员 {name}，花开有礼",
        "silver": f"银卡会员 {name}，欢迎回来",
        "gold": f"金卡会员 {name}，尊享花事",
        "diamond": f"钻石会员 {name}，花间最高礼遇",
    }
    return {
        "title": titles.get(code, f"{level_name} {name}，欢迎回来"),
        "home_title": f"欢迎回来，{name}",
        "text": texts.get(code, f"{name}，欢迎回到{SHOP_NAME}。{SLOGAN}。"),
        "role": "member",
        "level_code": code,
        "level_name": level_name,
        "badge_class": LEVEL_STYLE.get(code, "lv-normal"),
        "perk": perk,
        "progress": progress,
    }
