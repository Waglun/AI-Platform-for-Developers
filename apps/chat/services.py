from apps.chat.models import Conversation, Message
from apps.catalog.models import Apartment


def search_apartments(answers):
    queryset = Apartment.objects.filter(
        floor__section__building__stage__complex__external_id="1368",
        source_type=Apartment.SourceType.FLAT,
        source_status=Apartment.SourceStatus.AVAILABLE,
        price_rub__gt=0,
    ).select_related(
        "floor",
        "floor__section",
        "floor__section__building",
        "floor__section__building__stage",
        "floor__section__building__stage__complex",
    )

    rooms = answers.get("rooms")
    budget = answers.get("budget")
    min_area = answers.get("min_area")
    max_area = answers.get("max_area")

    if rooms is not None:
        queryset = queryset.filter(rooms=rooms)

    if budget is not None:
        queryset = queryset.filter(price_rub__lte=budget)

    if min_area is not None:
        queryset = queryset.filter(area_m2__gte=min_area)

    if max_area is not None:
        queryset = queryset.filter(area_m2__lte=max_area)

    return queryset.order_by("price_rub")


def format_apartment_results(apartments):
    if not apartments.exists():
        return (
            "К сожалению, по вашим параметрам пока не удалось "
            "найти подходящие квартиры. Попробуйте изменить условия поиска."
        )

    results = []

    for apartment in apartments[:5]:
        complex_name = apartment.floor.section.building.stage.complex.name

        results.append(
            f"Квартира №{apartment.number}\n"
            f"ЖК: {complex_name}\n"
            f"Комнат: {apartment.rooms}\n"
            f"Площадь: {apartment.area_m2} м²\n"
            f"Этаж: {apartment.floor.number}\n"
            f"Цена: {apartment.price_rub:,.0f} ₽".replace(",", " ")
        )

    return (
        f"Нашёл несколько подходящих вариантов:\n\n"
        + "\n\n".join(results)
    )


SCENARIOS = {
    "apartment_search": {
        "flow": "apartment_search",
        "step": "rooms",
        "content": "Отлично! Давайте подберём квартиру. Сколько комнат вы рассматриваете?",
        "actions": [
            {"id": "rooms_1", "label": "1 комната"},
            {"id": "rooms_2", "label": "2 комнаты"},
            {"id": "rooms_3", "label": "3 комнаты"},
            {"id": "rooms_4", "label": "4+ комнаты"},
        ],
    },
    "complex_info": {
        "flow": "complex_info",
        "step": "topic",
        "content": "С удовольствием расскажу о жилом комплексе. Что вас интересует?",
        "actions": [
            {"id": "location", "label": "Расположение"},
            {"id": "infrastructure", "label": "Инфраструктура"},
            {"id": "buildings", "label": "Дома и сроки сдачи"},
            {"id": "purchase_terms", "label": "Условия покупки"},
        ],
    },
    "showing": {
        "flow": "showing",
        "step": "apartment",
        "content": "Отлично! Давайте запишем вас на показ. Вы уже выбрали квартиру или хотите сначала посмотреть варианты?",
        "actions": [
            {"id": "selected_apartment", "label": "Квартира уже выбрана"},
            {"id": "need_apartment", "label": "Помогите выбрать"},
        ],
    },
}


def start_scenario(conversation, action):
    scenario = SCENARIOS[action]

    conversation.context = {
        "mode": "scenario",
        "flow": scenario["flow"],
        "step": scenario["step"],
        "answers": {},
    }
    conversation.save(update_fields=["context"])

    return Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=scenario["content"],
        metadata={
            "type": "scenario",
            "actions": scenario["actions"],
        },
    )


def get_area_actions(rooms):
    area_actions = {
        1: [
            {"id": "area_40_45", "label": "40–45 м²"},
            {"id": "area_45_50", "label": "45–50 м²"},
            {"id": "area_50_plus", "label": "От 50 м²"},
        ],
        2: [
            {"id": "area_60_65", "label": "60–65 м²"},
            {"id": "area_65_70", "label": "65–70 м²"},
            {"id": "area_70_plus", "label": "От 70 м²"},
        ],
        3: [
            {"id": "area_60_70", "label": "60–70 м²"},
            {"id": "area_70_85", "label": "70–85 м²"},
            {"id": "area_85_plus", "label": "От 85 м²"},
        ],
        4: [],
    }

    actions = area_actions.get(rooms, [])
    return actions + [
        {"id": "area_any", "label": "Любая площадь"}
    ]


def process_scenario_action(conversation, action):
    context = conversation.context
    flow = context.get("flow")
    step = context.get("step")

    if flow == "apartment_search" and step == "rooms":
        rooms_mapping = {
            "rooms_1": 1,
            "rooms_2": 2,
            "rooms_3": 3,
            "rooms_4": 4,
        }

        if action not in rooms_mapping:
            return None

        context["answers"]["rooms"] = rooms_mapping[action]
        context["step"] = "budget"

        conversation.context = context
        conversation.save(update_fields=["context"])

        return Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Какой бюджет вы рассматриваете?",
            metadata={
                "type": "scenario",
                "actions": [
                    {"id": "budget_5", "label": "До 5 млн ₽"},
                    {"id": "budget_8", "label": "До 8 млн ₽"},
                    {"id": "budget_10", "label": "До 10 млн ₽"},
                    {"id": "budget_any", "label": "Рассмотрю разные варианты"},
                ],
            },
        )

    if flow == "apartment_search" and step == "budget":
        budget_mapping = {
            "budget_5": 5_000_000,
            "budget_8": 8_000_000,
            "budget_10": 10_000_000,
            "budget_any": None,
        }

        if action not in budget_mapping:
            return None

        context["answers"]["budget"] = budget_mapping[action]
        context["step"] = "area"

        conversation.context = context
        conversation.save(update_fields=["context"])

        return Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Какую площадь квартиры вы рассматриваете?",
            metadata={
                "type": "scenario",
                "actions": get_area_actions(context["answers"]["rooms"]),
            },
        )

    if flow == "apartment_search" and step == "area":
        area_mapping = {
            "area_40_45": (40, 45),
            "area_45_50": (45, 50),
            "area_50_plus": (50, None),

            "area_60_65": (60, 65),
            "area_65_70": (65, 70),
            "area_70_plus": (70, None),

            "area_60_70": (60, 70),
            "area_70_85": (70, 85),
            "area_85_plus": (85, None),

            "area_any": (None, None),
        }

        if action not in area_mapping:
            return None

        min_area, max_area = area_mapping[action]

        context["answers"]["min_area"] = min_area
        context["answers"]["max_area"] = max_area
        context["step"] = "results"

        apartments = search_apartments(context["answers"])

        conversation.context = context
        conversation.save(update_fields=["context"])

        return Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=format_apartment_results(apartments),
            metadata={
                "type": "apartment_results",
                "count": apartments.count(),
            },
        )
