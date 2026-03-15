from pyboy import PyBoy

pyboy = PyBoy("rom.gb")

while pyboy.tick():
    pass

pyboy.stop()
