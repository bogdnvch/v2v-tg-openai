from aiogram.fsm.state import StatesGroup, State


class UserInfo(StatesGroup):
    thread_id = State()

