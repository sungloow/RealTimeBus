import os

import toml

class Config:
    def __init__(self):
        self.config = toml.load(os.path.join(os.path.dirname(__file__), "config.toml"))

    def get(self, section, key=None, default=None):
        section_data = self.config.get(section, {})
        if key:
            return section_data.get(key, default)
        return section_data

config = Config()
