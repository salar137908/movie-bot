from sqlalchemy import func, select, update

from database import FileItem, RequiredChannel, SectionRequiredChannel, SessionLocal, User


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
        result = await session.execute(select(FileItem).order_by(FileItem.id.desc()).limit(limit))
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


async def add_required_channel(chat_id: str, link: str | None = None, title: str | None = None) -> RequiredChannel:
    async with SessionLocal() as session:
        result = await session.execute(select(RequiredChannel).where(RequiredChannel.chat_id == str(chat_id)))
        item = result.scalar_one_or_none()
        if item is None:
            item = RequiredChannel(chat_id=str(chat_id), link=link, title=title, is_active=True)
            session.add(item)
        else:
            item.link = link
            item.title = title
            item.is_active = True
        await session.commit()
        await session.refresh(item)
        return item


async def get_required_channels(active_only: bool = False) -> list[RequiredChannel]:
    async with SessionLocal() as session:
        stmt = select(RequiredChannel).order_by(RequiredChannel.id.desc())
        if active_only:
            stmt = select(RequiredChannel).where(RequiredChannel.is_active.is_(True)).order_by(RequiredChannel.id.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def disable_required_channel(channel_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(select(RequiredChannel).where(RequiredChannel.id == int(channel_id)))
        item = result.scalar_one_or_none()
        if item is None:
            return False
        item.is_active = False
        await session.commit()
        return True


async def clear_required_channels() -> None:
    async with SessionLocal() as session:
        await session.execute(update(RequiredChannel).values(is_active=False))
        await session.commit()


async def count_required_channels() -> int:
    async with SessionLocal() as session:
        result = await session.execute(select(func.count(RequiredChannel.id)).where(RequiredChannel.is_active.is_(True)))
        return int(result.scalar() or 0)



async def add_section_required_channel(section_key: str, chat_id: str, link: str | None = None, title: str | None = None) -> SectionRequiredChannel:
    async with SessionLocal() as session:
        section_key = str(section_key).strip()
        chat_id = str(chat_id).strip()
        result = await session.execute(
            select(SectionRequiredChannel).where(
                SectionRequiredChannel.section_key == section_key,
                SectionRequiredChannel.chat_id == chat_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            item = SectionRequiredChannel(section_key=section_key, chat_id=chat_id, link=link, title=title, is_active=True)
            session.add(item)
        else:
            item.link = link
            item.title = title
            item.is_active = True
        await session.commit()
        await session.refresh(item)
        return item


async def get_section_required_channels(section_key: str | None = None, active_only: bool = False) -> list[SectionRequiredChannel]:
    async with SessionLocal() as session:
        stmt = select(SectionRequiredChannel).order_by(SectionRequiredChannel.section_key.asc(), SectionRequiredChannel.id.desc())
        if section_key:
            stmt = stmt.where(SectionRequiredChannel.section_key == str(section_key).strip())
        if active_only:
            stmt = stmt.where(SectionRequiredChannel.is_active.is_(True))
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def disable_section_required_channel(channel_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(select(SectionRequiredChannel).where(SectionRequiredChannel.id == int(channel_id)))
        item = result.scalar_one_or_none()
        if item is None:
            return False
        item.is_active = False
        await session.commit()
        return True


async def clear_section_required_channels(section_key: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(SectionRequiredChannel)
            .where(SectionRequiredChannel.section_key == str(section_key).strip())
            .values(is_active=False)
        )
        await session.commit()


async def count_section_required_channels(section_key: str | None = None) -> int:
    async with SessionLocal() as session:
        stmt = select(func.count(SectionRequiredChannel.id)).where(SectionRequiredChannel.is_active.is_(True))
        if section_key:
            stmt = stmt.where(SectionRequiredChannel.section_key == str(section_key).strip())
        result = await session.execute(stmt)
        return int(result.scalar() or 0)


async def update_required_channel(channel_id: int, chat_id: str, link: str | None = None, title: str | None = None) -> RequiredChannel | None:
    async with SessionLocal() as session:
        result = await session.execute(select(RequiredChannel).where(RequiredChannel.id == int(channel_id)))
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.chat_id = str(chat_id).strip()
        item.link = link
        item.title = title
        item.is_active = True
        await session.commit()
        await session.refresh(item)
        return item


async def update_section_required_channel(channel_id: int, chat_id: str, link: str | None = None, title: str | None = None) -> SectionRequiredChannel | None:
    async with SessionLocal() as session:
        result = await session.execute(select(SectionRequiredChannel).where(SectionRequiredChannel.id == int(channel_id)))
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.chat_id = str(chat_id).strip()
        item.link = link
        item.title = title
        item.is_active = True
        await session.commit()
        await session.refresh(item)
        return item
