"""Продающее описание объявления ATOMM.STORE.

Разрешённые Авито теги: p, br, strong, em, ul, ol, li. Без телефонов, ссылок и мессенджеров.
Факты о магазине — только подтверждённые владельцем (см. STORE).
"""
from xml.sax.saxutils import escape

STORE = {
    "name": "ATOMM.STORE",
    "years": 10,
    "warranty": "12 месяцев",
    "address": "Москва, Багратионовский проезд, 7к2",
    "hours": "с 12:00 до 18:00",
}

SIM_TEXT = {
    "SIM + eSIM": "nano-SIM + eSIM",
    "Только eSIM": "только eSIM, без лотка. eSIM поддерживают МТС, Билайн, МегаФон, Т2 и другие — "
                   "подключается в салоне или в приложении оператора",
    "2 SIM": "две nano-SIM",
}
REGION_TEXT = {"EU": "европейская", "US": "американская", "CN": "китайская", "IN": "индийская",
               "JP": "японская", "HK": "гонконгская", "GB": "британская", "AE": "ОАЭ", "KR": "корейская",
               "KZ": "казахстанская", "CA": "канадская", "CL": "чилийская", "AU": "австралийская",
               "ZA": "южноафриканская", "AM": "армянская", "PY": "парагвайская", "ID": "индонезийская"}


def specs(it, prof):
    rows = []
    if prof.get("Model"):
        rows.append(("Модель", f"{prof.get('Vendor', '')} {prof['Model']}".strip()))
    if it.get("memory"):
        rows.append(("Память", it["memory"]))
    if it.get("ram"):
        rows.append(("Оперативная память", it["ram"]))
    if it.get("color_src"):
        ru = prof.get("Color")
        name = it.get("color_official") or it["color_src"]
        rows.append(("Цвет", f"{name} ({ru})" if ru and ru[0].islower() else name))
    if it.get("sim") in SIM_TEXT:
        rows.append(("SIM", SIM_TEXT[it["sim"]]))
    if it.get("region") in REGION_TEXT:
        rows.append(("Версия", REGION_TEXT[it["region"]] + (" (США)" if it["region"] == "US" else "")))
    if it.get("chip"):
        rows.append(("Процессор", it["chip"]))
    rows += [tuple(r) for r in it.get("extra_specs", [])]
    return rows


def description(it, prof):
    title = escape(it["title"].replace(", новый", ""))
    rows = "".join(f"<li>{escape(k)}: {escape(str(v))}</li>" for k, v in specs(it, prof))
    return (
        f"<p><strong>{title}</strong> — новый, не активирован, в заводской плёнке. "
        f"Гарантия магазина {STORE['warranty']}.<br>"
        f"📍 В наличии — заберите сегодня: {STORE['address']}, {STORE['hours']}. Есть доставка курьером.<br>"
        "💵 Оплата только наличными — при самовывозе или курьеру при получении.</p>"

        "<p><strong>Цена в объявлении — окончательная.</strong> Без трейд-ина, рассрочки и доплат. "
        "Часто в чате отвечают «эта цена при сдаче старого телефона» — у нас такого нет. "
        "Цена обновляется каждое утро.</p>"

        f"<p><strong>Характеристики</strong></p><ul>{rows}</ul>"

        "<p><strong>Что вы получаете</strong></p><ul>"
        "<li>Новое устройство: не восстановленное, не активированное, коробка в заводской плёнке</li>"
        "<li>Серийный номер сверим по коробке на сайте производителя при вас, до оплаты</li>"
        f"<li>Гарантийный талон магазина на {STORE['warranty']}</li>"
        "</ul>"

        f"<p><strong>Почему {STORE['name']}</strong></p><ul>"
        f"<li>{STORE['years']} лет в продаже техники</li>"
        "<li>Поддержка 24/7 в чате Авито — до и после покупки</li>"
        "<li>Бесплатная консультация: подскажем модель, память и версию SIM</li>"
        "</ul>"

        "<p>Напишите в чат — забронируем по цене из объявления и договоримся о самовывозе или доставке. "
        "Другая память или цвет — в блоке «Варианты».</p>"
    )
