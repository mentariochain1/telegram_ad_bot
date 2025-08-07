from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_channel_info = State()
    waiting_for_channel_verification = State()


class CampaignStates(StatesGroup):
    waiting_for_ad_text = State()
    waiting_for_price = State()
    waiting_for_confirmation = State()