class GameNotFound(Exception):
    """Raised when game with given name is not found"""

    def __init__(self, game_name: str, *args: object) -> None:
        self.game_name = game_name
        super().__init__(*args)

    def __str__(self) -> str:
        return f"Game {self.game_name} not found"


class NoLoadFunction(Exception):
    """Raised when game module does not have a load function"""

    def __init__(self, game_name: str, *args: object) -> None:
        self.game_name = game_name
        super().__init__(*args)

    def __str__(self) -> str:
        return f"Game {self.game_name} not found"


class ActiveGameNotFound(Exception):
    """Raised when game is not found in game status store"""

    def __str__(self) -> str:
        return "Game not found"


class NotEnoughPlayers(Exception):
    """Raised when game is trying to initialize with not enough players"""

    def __init__(self, player_count: int, min_player_count: int, *args: object) -> None:
        self.player_count = player_count
        self.min_player_count = min_player_count
        super().__init__(*args)

    def __str__(self) -> str:
        return f"This game supports up to {self.min_player_count} players but you tryed to play with {self.player_count} players!"


class ToManyPlayers(Exception):
    """Raised when game is trying to initialize with to many players"""

    def __init__(self, player_count: int, max_player_count: int, *args: object) -> None:
        self.player_count = player_count
        self.max_player_count = max_player_count
        super().__init__(*args)

    def __str__(self) -> str:
        return f"This game supports up to {self.max_player_count} players but you tryed to play with {self.player_count} players!"
