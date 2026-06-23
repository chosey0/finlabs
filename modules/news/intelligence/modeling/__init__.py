"""Surge-ranking model scaffold: dataset loading, features, models, evaluation.

The training target is the continuous, per-stock time-series standardized abnormal
return (``abnormal_return_std``); the model's prediction is the ``surge_score`` used
to rank a day's candidates, with a binary surge probability as an auxiliary view.

Heavy dependencies are optional: the text embedder and the model are protocols with
pure-Python defaults (a hashing embedder and a ridge regressor) so the whole
pipeline runs and is tested without LightGBM or a transformer. Production adapters
(LightGBM, a Korean sentence encoder) slot in behind the same protocols.
"""
