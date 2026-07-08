from graph import graph
from db import reset_db_db
from langgraph.types import Command
import asyncio

reset_db_db()
config={"configurable":{"thread_id":"approve-debug"}}
input_messages={"messages":[("user","I want 2 Veg Burgers")]}

async def main():
    async for event in graph.astream(input_messages, config=config, stream_mode='values'):
        print('EVENT_KEYS', list(event.keys()))
        if 'messages' in event:
            print('LAST_MSG', event['messages'][-1])
    state = graph.get_state(config)
    print('STATE_NEXT', state.next)
    print('STATE_VALUES', state.values)
    result = await graph.ainvoke(Command(resume={'decision':'approve','note':'ok'}), config=config)
    print('RESULT', result)

asyncio.run(main())
