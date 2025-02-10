from klibs.KLStructure import FactorSet
from klibs import P

condition = None
conditions = {"25": [True, (False, 3)], "50": [True, False], "75": [(True, 3), False]}

if P.condition is None:
    raise RuntimeError(
        "Condition was not specified!\nMust be one of 25, 50, 75 (e.g., klibs run 24 -c 25)"
    )

else:
    condition = str(P.condition)

probabilities = conditions[condition]

if probabilities is None:
    raise RuntimeError(f"Invalid condition flag supplied!\nMust be one of [25, 50, 75], but got {P.condition}")

exp_factors = FactorSet({"target_trial": probabilities})
