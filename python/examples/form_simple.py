# pip install hyperplatform
import asyncio
from hyperplatform import Bot, Dispatcher, Router, Message, Form, FormRow, TextInput, CallbackQuery

BOT_API_BASE = 'https://api.hyperplatform.io/bot'  # Replace with your local url if applicable
BOT_API_TOKEN = '<YOUR_BOT_TOKEN>'

router = Router()


# Send form
@router.message()
async def send_form(msg: Message):
    field = TextInput(id='field1', placeholder='Type something...')
    row = FormRow(elements=[field])
    form = Form(title='The form', description='My form', rows=[row])
    await msg.bot.send_form(chat_id=msg.chat_id, form=form)


# Get form data
@router.callback_query()
async def receive_form(cb: CallbackQuery):
    print(cb.form_data)


bot = Bot(base_url=BOT_API_BASE, token=BOT_API_TOKEN)
dp = Dispatcher(router)


async def main():
    try:
        await dp.start_polling(bot)
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
