from apps.catalog.search import search_catalog


def search_apartments(answers):
    params = dict(answers)
    if answers.get("budget") is not None:
        params["max_price"] = answers["budget"]
    return search_catalog(params)


def format_apartment_results(apartments, has_more=False):
    if not apartments:
        return (
            "К сожалению, по вашим параметрам пока не удалось "
            "найти подходящие квартиры. Попробуйте изменить условия поиска."
        )

    results = []

    for apartment in apartments:
        complex_name = apartment.floor.section.building.stage.complex.name

        results.append(
            f"Квартира №{apartment.number}\n"
            f"ЖК: {complex_name}\n"
            f"Комнат: {apartment.rooms}\n"
            f"Площадь: {apartment.area_m2} м²\n"
            f"Этаж: {apartment.floor.number}\n"
            f"Цена: {apartment.price_rub:,.0f} ₽".replace(",", " ")
        )

    content = "Нашёл несколько подходящих вариантов:\n\n" + "\n\n".join(results)

    if has_more:
        content += "\n\nМогу показать следующие варианты."

    return content


def get_apartment_results(answers, page=1, page_size=5):
    page = max(1, page)
    queryset = search_apartments(answers)
    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    apartments = list(queryset[start:end])
    return {
        "content": format_apartment_results(
            apartments,
            has_more=end < total_count,
        ),
        "count": total_count,
        "page_count": len(apartments),
        "apartment_ids": [apartment.pk for apartment in apartments],
        "page": page,
        "has_more": end < total_count,
    }
