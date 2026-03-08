"""Betting-model training, backtesting, and prediction workflows."""

from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    ModelMarket,
    StrategyMarket,
    load_artifact,
)
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_UNIT_SIZE,
    BacktestOptions,
    BacktestSummary,
    backtest_betting_model,
)
from cbb.modeling.infer import (
    PredictionOptions,
    PredictionSummary,
    predict_best_bets,
)
from cbb.modeling.policy import BetPolicy, PlacedBet
from cbb.modeling.train import (
    DEFAULT_EPOCHS,
    DEFAULT_L2_PENALTY,
    DEFAULT_LEARNING_RATE,
    DEFAULT_MIN_EXAMPLES,
    DEFAULT_MODEL_SEASONS_BACK,
    LogisticRegressionConfig,
    TrainingOptions,
    TrainingSummary,
    resolve_training_seasons,
    score_examples,
    train_betting_model,
)

__all__ = [
    "BacktestOptions",
    "BacktestSummary",
    "BetPolicy",
    "DEFAULT_ARTIFACT_NAME",
    "DEFAULT_BACKTEST_RETRAIN_DAYS",
    "DEFAULT_EPOCHS",
    "DEFAULT_L2_PENALTY",
    "DEFAULT_LEARNING_RATE",
    "DEFAULT_MIN_EXAMPLES",
    "DEFAULT_MODEL_SEASONS_BACK",
    "DEFAULT_STARTING_BANKROLL",
    "DEFAULT_UNIT_SIZE",
    "LogisticRegressionConfig",
    "ModelArtifact",
    "ModelMarket",
    "PlacedBet",
    "PredictionOptions",
    "PredictionSummary",
    "StrategyMarket",
    "TrainingOptions",
    "TrainingSummary",
    "backtest_betting_model",
    "load_artifact",
    "predict_best_bets",
    "resolve_training_seasons",
    "score_examples",
    "train_betting_model",
]
