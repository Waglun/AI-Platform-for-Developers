from apps.chat.models import Conversation, Message


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
        context["step"] = "search"

        conversation.context = context
        conversation.save(update_fields=["context"])

        return Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Отлично! Подбираю подходящие квартиры по вашим параметрам.",
            metadata={
                "type": "scenario",
                "actions": [],
            },
        )
