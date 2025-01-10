from klibs.KLStructure import FactorSet
from klibs import P

probabilities = []

if P.condition == "75":
    probabilities = [(True, 3), False]
elif P.condition == "25":
    probabilities = [True, (False, 3)]
else:
    probabilites = [True, False]

exp_factors = FactorSet({"target_trial": probabilities})
