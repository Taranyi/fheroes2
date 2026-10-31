###########################################################################
#   fheroes2: https://github.com/ihhub/fheroes2                           #
#   Copyright (C) 2026                                                    #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
###########################################################################

"""Same shared candidate actor, computed only for real (bias=1) candidate rows."""

import battle_ppo


class PackedCandidatePolicy(battle_ppo.CandidatePolicy):
    """Skip padded actor rows; retain the original critic, architecture and mask distribution."""
    def get_distribution(self, obs, action_masks=None):
        valid = obs[:, :, 0] != 0
        features = obs.float()
        logits = features.new_zeros(obs.shape[:2])
        logits[valid] = self.actor(features[valid]).squeeze(-1)
        distribution = self.action_dist.proba_distribution(action_logits=logits)
        distribution.apply_masking(action_masks if action_masks is not None else valid)
        return distribution
