"""TODO Change confirm wording to accept"""


import random
import string
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, List, Literal, Mapping, Optional

import redis.asyncio as redis_sync
import redis.asyncio.client as redis_async_client

from data_types import GameId, UserId
from exceptions import GameNotFound, UserNotFound

from .utils import RedisDb, is_main_instance, pipeline_watch


class GameStatus(RedisDb):
    """
    API wrapper for reddis db which handles the status of games
    all entrys have a shadow key to keep track of when games expire.
    This allows for the game status to be retrevied after the game has expired.

    IMPORTANT: For the games to expire properly the start_expire_listener function
    must be called before any games are added to the db

    All data in the db is in form
    GameId: GameState
    """

    __db_number = 1
    __pool = redis_sync.Redis(db=__db_number)

    @dataclass
    class Game:
        """
        Dataclass for game state

        Used to store data on all games no matter the game type

        status[int]:
            0 = unaccepted | 1 = accepted but queued | 2 = in progress

        game_module_name[str]:
            Name of game module

        starting_user[int]:
            User id of user who started the game

        usernames[Mapping[str, str]]:
            Mapping of user id to user name

        #TODO UPDATE THIS


        """

        status: Literal[0, 1, 2]
        game_module_name: str
        starting_user: int
        usernames: Dict[str, str]
        all_users: List[UserId]
        pending_users: List[UserId]

        def confirmed_users(self) -> List[UserId]:
            """
            Returns a list of all confirmed users
            """

            return list(
                filter(
                    lambda user_id: user_id not in self.pending_users,
                    self.all_users,
                )
            )

    # Callbacks for when games expire
    __expire_callbacks: dict[str, Callable[[GameId], Awaitable[None]]] = {}

    @staticmethod
    def __get_shadow_key(game_id: GameId) -> str:
        """
        Returns the shadow key version of a game_id
        """

        return f"shadowKey:{game_id}"

    @staticmethod
    def __create_game_id() -> GameId:
        """
        Generates a random game id and returns it
        """

        return "".join(random.choices(string.ascii_letters + string.digits, k=16))

    @staticmethod
    async def add(game_status: Game, expire_time: timedelta) -> GameId:
        """
        Adds a game to the db

        Returns the game id
        """

        game_id = GameStatus.__create_game_id()

        await GameStatus.__pool.json().set(game_id, ".", asdict(game_status))

        # Creates shadow key that expires so that the game
        # can be retrevied after it expires
        shadow_key = GameStatus.__get_shadow_key(game_id)
        await GameStatus.__pool.set(shadow_key, -1)
        await GameStatus.__pool.expire(shadow_key, expire_time)

        return game_id

    @staticmethod
    async def get(game_id: GameId) -> Game:
        """
        Returns game data if game is found

        Raises ActiveGameNotFound if game is not found
        """

        if game_state := await GameStatus.__pool.json().get(game_id):
            return GameStatus.Game(**game_state)
        raise GameNotFound(game_id)

    @staticmethod
    async def set_expiry(game_id: GameId, extend_time: Optional[timedelta]):
        """
        Sets the amount of time before a game expires
        """

        shadow_key = GameStatus.__get_shadow_key(game_id)
        if extend_time:
            # Only need to update shadow key cause it is the only one that expires
            await GameStatus.__pool.expire(shadow_key, extend_time)
        else:
            await GameStatus.__pool.persist(shadow_key)

    @staticmethod
    async def set_game_unconfirmed(game_id: GameId):
        await GameStatus.__pool.json().set(game_id, ".status", 0)

    @staticmethod
    async def set_game_queued(game_id: GameId):
        await GameStatus.__pool.json().set(game_id, ".status", 1)

    @staticmethod
    async def set_game_in_progress(game_id: GameId):
        await GameStatus.__pool.json().set(game_id, ".status", 2)

    @staticmethod
    @pipeline_watch(__pool, "game_id", GameNotFound)
    async def user_accepted(
        pipe: redis_async_client.Pipeline,
        game_id: GameId,
        user_id: int,
    ) -> List[int]:
        """
        Adds a user to the confirmed list and removes them from the
        unconfirmed list

        Raises ActiveGameNotFound if game is not found
        Raises UserNotFound if user is not in unconfirmed list

        Returns updated unconfirmed_users list
        """

        game_status = await GameStatus.get(game_id)

        if user_id in game_status.pending_users:
            # Switch to buffered modweeke to make sure all commands
            # are executed without any external changes to the lists
            pipe.multi()
            # Moves user from unconfirmed to confirmed list
            pipe.json().arrpop(
                game_id,
                ".pending_users",
                game_status.pending_users.index(user_id),
            )
            pipe.json().get(game_id, ".pending_users")
            results = await pipe.execute()

            return results[1]

        else:
            raise UserNotFound(user_id)

    @staticmethod
    async def delete(game_id: GameId):
        """
        Deletes game status from db
        """

        await GameStatus.__pool.delete(game_id)

        # Deletes shadow key cause their expire event could be listened to
        shadow_key = GameStatus.__get_shadow_key(game_id)
        await GameStatus.__pool.delete(shadow_key)

    @staticmethod
    def handle_game_expire(
        fn: Callable[[GameId], Awaitable[None]]
    ) -> Callable[[GameId], Awaitable[None]]:
        if (name := fn.__name__) not in GameStatus.__expire_callbacks:
            GameStatus.__expire_callbacks[name] = fn

        return fn

    @staticmethod
    @RedisDb.is_pubsub_callback(f"__keyevent@{__db_number}__:expired")
    async def __expire_handler(msg: Any):
        """
        Handler for when a key expires

        Runs all the callbacks registed with the add_expire_handler function.

        Raises Exception if message is not in utf-8 format
        Raises Exception if unknown error occurs
        Raises ActiveGameNotFound if the expired game is not found
        """

        try:
            msg = msg["data"].decode("utf-8")
        except AttributeError:
            raise ValueError("Message not in utf-8 format")
        else:
            # Checks if message is a shadow key
            if msg.startswith(GameStatus.__get_shadow_key("")):
                game_id = msg.split(":")[1]

                expired_game_data = await GameStatus.get(game_id)

                for callback in GameStatus.__expire_callbacks.values():
                    await callback(game_id)
            else:
                print("Not shadow key")

    @staticmethod
    @is_main_instance
    async def remove_expire_handler(
        game_expire_callback: Callable[[GameId, Game], Awaitable[None]]
    ):
        """
        Removes a callback from the list of callbacks to be called when a key expires
        """

        if (name := game_expire_callback.__name__) not in GameStatus.__expire_callbacks:
            raise KeyError("Callback with that name not found")

        else:
            del GameStatus.__expire_callbacks[name]
