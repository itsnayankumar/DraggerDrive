from os.path import splitext
import re
from bot.config import Telegram
from bot.helper.database import Database
from bot.telegram import StreamBot, UserBot
from bot.helper.file_size import get_readable_file_size
from bot.helper.cache import get_cache, save_cache
from asyncio import gather

db = Database()


async def fetch_message(chat_id, message_id):
    try:
        message = await StreamBot.get_messages(chat_id, message_id)
        return message
    except Exception as e:
        return None


async def get_messages(chat_id, first_message_id, last_message_id, batch_size=50):
    messages = []
    current_message_id = first_message_id
    while current_message_id <= last_message_id:
        batch_message_ids = list(range(current_message_id, min(current_message_id + batch_size, last_message_id + 1)))
        tasks = [fetch_message(chat_id, message_id) for message_id in batch_message_ids]
        batch_messages = await gather(*tasks)
        for message in batch_messages:
            if message:
                if file := message.video or message.document:
                    title = file.file_name or message.caption or file.file_id
                    title, _ = splitext(title)
                    title = re.sub(r'[.,|_\',]', ' ', title)
                    messages.append({"msg_id": message.id, "title": title,
                                     "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size),
                                     "type": file.mime_type, "chat_id": str(chat_id)})
        current_message_id += batch_size
    return messages


async def get_files(chat_id, page=1):
    if Telegram.SESSION_STRING == '':
        return await db.list_tgfiles(id=chat_id, page=page)
    if cache := get_cache(chat_id, int(page)):
        return cache
    posts = []
    async for post in UserBot.get_chat_history(chat_id=int(chat_id), limit=50, offset=(int(page) - 1) * 50):
        file = post.video or post.document
        if not file:
            continue
        title = file.file_name or post.caption or file.file_id
        title, _ = splitext(title)
        title = re.sub(r'[.,|_\',]', ' ', title)
        posts.append({"msg_id": post.id, "title": title,
                      "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size), "type": file.mime_type})
    save_cache(chat_id, {"posts": posts}, page)
    return posts


async def posts_file(posts, chat_id):
    # Prepare the Clean Chat ID (remove -100 prefix)
    clean_chat_id = str(chat_id).replace("-100", "")

    phtml = """
    <div class="col">
        <div class="card text-white bg-primary mb-3 position-relative" style="overflow: hidden;">
            
            <input type="checkbox" class="admin-only form-check-input position-absolute top-0 end-0 m-2"
                onchange="checkSendButton()" id="selectCheckbox"
                data-id="{id}|{hash}|{title}|{size}|{type}|{img}" style="z-index: 20;">
            
            <div style="position: relative;">
                <img src="https://cdn.jsdelivr.net/gh/weebzone/weebzone/data/Surf-TG/src/loading.gif" 
                     class="lzy_img card-img-top rounded-top"
                     data-src="{img}" alt="{title}" 
                     style="height: 160px; object-fit: cover; width: 100%;">
                
                <button onclick="event.preventDefault(); deleteFile('{clean_chat_id}', '{id}')" 
                        class="btn btn-danger btn-sm position-absolute shadow-sm" 
                        style="bottom: 8px; right: 8px; border-radius: 50%; width: 32px; height: 32px; padding: 0; display: flex; align-items: center; justify-content: center; z-index: 20;"
                        title="Delete this file">
                    🗑
                </button>
            </div>
            
            <a href="/watch/{clean_chat_id}?id={id}&hash={hash}" style="text-decoration: none; color: white;">
                <div class="card-body p-2">
                    <h6 class="card-title text-truncate" style="font-size: 0.9rem; margin-bottom: 5px;">{title}</h6>
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="badge bg-warning text-dark" style="font-size: 0.7rem;">{type}</span>
                        <span class="badge bg-info text-dark" style="font-size: 0.7rem;">{size}</span>
                    </div>
                </div>
            </a>
        </div>
    </div>
    """
    
    return ''.join(phtml.format(
        clean_chat_id=clean_chat_id, 
        id=post["msg_id"], 
        img=f"/api/thumb/{clean_chat_id}?id={post['msg_id']}", 
        title=post["title"], 
        hash=post["hash"], 
        size=post['size'], 
        type=post['type']
    ) for post in posts)
