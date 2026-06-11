from sqlalchemy import func, select

from database import FileItem, SessionLocal, User


async def save_user(telegram_id: int, username: str | None, full_name: str | None) -> User:
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
        else:
            user.username = username
            user.full_name = full_name
        await session.commit()
        await session.refresh(user)
        return user


async def add_file(
    title: str,
    archive_chat_id: str,
    archive_message_id: int,
    telegram_file_id: str | None = None,
    file_type: str | None = None,
) -> FileItem:
    async with SessionLocal() as session:
        item = FileItem(
            title=title,
            archive_chat_id=str(archive_chat_id),
            archive_message_id=int(archive_message_id),
            telegram_file_id=telegram_file_id,
            file_type=file_type,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def get_file(file_id: int) -> FileItem | None:
    async with SessionLocal() as session:
        result = await session.execute(select(FileItem).where(FileItem.id == file_id))
        return result.scalar_one_or_none()


async def get_files(limit: int = 20) -> list[FileItem]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(FileItem).order_by(FileItem.id.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def disable_file(file_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(select(FileItem).where(FileItem.id == file_id))
        item = result.scalar_one_or_none()
        if item is None:
            return False
        item.is_active = False
        await session.commit()
        return True


async def increment_views(file_id: int) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(FileItem).where(FileItem.id == file_id))
        item = result.scalar_one_or_none()
        if item:
            item.views = (item.views or 0) + 1
            await session.commit()


async def count_users() -> int:
    async with SessionLocal() as session:
        result = await session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)


async def count_files() -> int:
    async with SessionLocal() as session:
        result = await session.execute(select(func.count(FileItem.id)))
        return int(result.scalar() or 0)
