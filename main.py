import asyncio

import zendriver as zd


async def main():
    browser = await zd.start()
    page = await browser.get('https://zendriver.dev/')

    elems = await page.select_all('*[src]')

    for elem in elems:
        await elem.flash()

    page2 = await browser.get('https://twitter.com', new_tab=True)
    page3 = await browser.get('https://github.com/ultrafunkamsterdam/nodriver', new_window=True)

    for p in (page, page2, page3):
        await p.bring_to_front()
        await p.scroll_down(200)
        await p   # wait for events to be processed
        await p.reload()
        if p != page3:
            await p.close()

if __name__ == '__main__':
    asyncio.run(main())
