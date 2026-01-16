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

async def choose_users(
        self,
        title: str,
        list_of_users: list[Player],
        amount: int,
        required: bool = True,
) -> list[Player]:
    fmt = [
        f"{idx}. {p.user}"
        f" {p.user.mention}"
        f" {self.game.get_role_name(self.revealed_roles[p]) if p in self.revealed_roles else ''}"
        for idx, p in enumerate(list_of_users, 1)
    ]

    if not required:
        fmt.insert(0, "0. Dismiss")
        prompt_msg = _(
            "**Type the number of the user to choose for this action. Type `0` to"
            f" dismiss. You need to choose {amount} more.**"
        )
        start_num = 0
    else:
        prompt_msg = _(
            "**Type the number of the user to choose for this action. You need to"
            f" choose {amount} more.**"
        )
        start_num = 1

    full_prompt_msg = prompt_msg.format(amount=amount)

    paginator = commands.Paginator(prefix="", suffix="")
    paginator.add_line(f"**{title}**")
    for i in fmt:
        paginator.add_line(i)

    for page in paginator.pages:
        await self.send(page)

    mymsg = await self.send(full_prompt_msg)

    if mymsg is None:
        await self.game.ctx.send(
            _(
                "I couldn't send a DM to someone. All players should allow me to"
                " send Direct Messages to them."
            )
        )

    chosen = []
    while len(chosen) < amount:
        def check(msg):
            return (
                    msg.author == self.user
                    and msg.content.isdigit()
                    and int(msg.content) >= start_num
                    and int(msg.content) <= len(list_of_users)
                    and msg.channel == mymsg.channel
            )

        try:
            msg = await self.game.ctx.bot.wait_for('message', check=check, timeout=self.game.timer)
        except asyncio.TimeoutError:
            await mymsg.edit(content=_("Time's up for choosing."))
            break

        choice_idx = int(msg.content) - 1

        if choice_idx == -1 and not required:
            return []

        player = list_of_users[choice_idx]
        if player in chosen:
            await self.send(
                _("🚫 You've chosen **{player}** already.").format(player=player.user)
            )
            continue

        if amount > 1:
            await self.send(
                _("**{player}** has been selected.").format(player=player.user)
            )

        chosen.append(player)
        await mymsg.edit(content=full_prompt_msg.format(amount=amount - len(chosen)))

    return chosen