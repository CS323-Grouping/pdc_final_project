class Player:
    def __init__(self, player_id, x=0, y=0, sprite_path="assets/placeholder_AI_Knight.png"):
        self.id = player_id
        self.x = x #+ offset
        self.y = y #+ offset need to set offset so it won't get drawn out of screen
        self.width = 50
        self.height = 50

    def something(self):
        pass
