"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

with open("data/db/schema.sql") as f:
    stuff = f.read().splitlines()

t = ""
c = []
in_t = False
for line in stuff:
    if line.startswith("CREATE TABLE"):
        t = line.split()[2].split(".")[1]
        in_t = True
        print(t)
    elif in_t:
        if line == ");":
            print(c)
            t = ""
            in_t = False
            c = []
        else:
            c.append(line.split()[0].strip('"'))
