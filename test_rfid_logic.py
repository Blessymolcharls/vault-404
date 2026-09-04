from app.core.engine import VaultAuthEngine, EngineConfig
from app.adapters.esp32_hardware import ESP32SerialAdapter
import asyncio

async def main():
    e = VaultAuthEngine(hardware=ESP32SerialAdapter())
    await e.start_authentication()
    print('State before:', e.state)
    print('Submitting wrong rfid (11223344)...')
    res = await e.submit_rfid('11223344')
    print('Res:', res)
    print('State after:', e.state)

asyncio.run(main())
