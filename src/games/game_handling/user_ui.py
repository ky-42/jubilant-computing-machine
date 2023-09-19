from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

import discord

from bot import bot
from data_types import GameId
from data_wrappers import GameStatus

# Stops circular import
if TYPE_CHECKING:
    from games.utils import GameDetails


def create_confirm_embed(
    player_id: int, game_state: GameStatus.GameState, game_details: GameDetails
) -> discord.Embed:
    message_embed = discord.Embed(
        title=f"{game_state.player_names[str(game_state.starting_player)]} wants to play a game!",
    )

    message_embed.add_field(name="Game", value=f"{game_state.game}", inline=True)

    # Gets list of other request users names
    other_player_names = [
        game_state.player_names[other_players_ids]
        for other_players_ids in game_state.player_names.keys()
        if other_players_ids != player_id
        and other_players_ids != game_state.starting_player
    ]

    # Adds other players names to embed
    if len(other_player_names):
        message_embed.add_field(
            name="Other Players", value=", ".join(other_player_names), inline=True
        )

    # Adds game thumbnail to embed
    file = discord.File(game_details.thumbnail_file_path, filename="abc.png")
    message_embed.set_thumbnail(url=f"attachment://{file.filename}")

    # Adds bet to embed
    if game_state.bet:
        message_embed.add_field(name="Bet", value=game_state.bet, inline=False)

    return message_embed


class GameConfirm(discord.ui.View):
    """
    UI for confirming a game
    """

    def __init__(
        self,
        game_id: GameId,
        accept_func: Callable[[int, GameId], Awaitable[None]],
        deny_func: Callable[[GameId], Awaitable[None]],
    ):
        self.game_id = game_id
        self.accept_func = accept_func
        self.deny_func = deny_func
        super().__init__()

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Will delete interaction after 5 seconds
        # if interaction.message:
        #     await interaction.message.edit(delete_after=5)

        await interaction.response.send_message("Game accepted!")

        await self.accept_func(interaction.user.id, self.game_id)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Will delete interaction after 5 seconds
        # if interaction.message:
        #     await interaction.message.edit(delete_after=5)
        game_details = await GameStatus.get(self.game_id)

        for player_id in game_details.confirmed_players:
            await bot.get_user(int(player_id)).send(
                f"{interaction.user.name} has rejected the game of {game_details.game} the you accepted"
            )

        await self.deny_func(self.game_id)

        await interaction.response.send_message("Game rejected!")
