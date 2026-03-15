from pyboy import PyBoy
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry

pyboy = PyBoy("rom.gb")
screen = ScreenReader(pyboy)
menu = MenuReader(pyboy, screen)
dialogue = DialogueAdvancer(pyboy, screen)
naming = NameEntry(pyboy)

# Skip intro and select New Game
menu.wait_for_main_menu()
pyboy.tick(30)
menu.select("NEW GAME")

# Advance Oak's dialogue and capture text
text = dialogue.advance_until(lambda d, u: menu.is_name_menu())
print("=== Oak's Speech ===")
print(text)

# Select NEW NAME and enter "JESS"
pyboy.tick(30)
options = menu.get_options()
print("\nName options:", options)
menu.select("NEW NAME", options)
naming.enter("JESS")
print("Name entered: JESS")

# Advance Oak's dialogue about the rival
rival_text = dialogue.advance_until(lambda d, u: menu.is_name_menu())
print("\n=== Oak's Speech (Rival) ===")
print(rival_text)

# Select NEW NAME and enter "FOLAGOR"
pyboy.tick(30)
rival_options = menu.get_options()
print("\nRival name options:", rival_options)
menu.select("NEW NAME", rival_options)
naming.enter("FOLAGOR")
print("Rival name entered: FOLAGOR")

# Advance remaining dialogue until player appears in bedroom
final_text = dialogue.advance_until(lambda d, u: d and u > 30)
print("\n=== Oak's Final Speech ===")
print(final_text)
print("\nPlayer is now in their bedroom!")

while pyboy.tick():
    pass

pyboy.stop()
