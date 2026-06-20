from hpsilab_mcp import HpsiMcpClient


def main() -> None:
    client = HpsiMcpClient()

    prediction = client.get_ai_prediction("NVDA")
    iv_radar = client.get_iv_radar("NVDA")
    option_pressure = client.get_option_pressure("SPY")
    monte_carlo = client.get_monte_carlo("QBTS")
    equity_curve = client.get_equity_curve("IONQ")

    print("AI Prediction:", prediction)
    print("IV Radar:", iv_radar)
    print("Option Pressure:", option_pressure)
    print("Monte Carlo:", monte_carlo)
    print("Equity Curve:", equity_curve)


if __name__ == "__main__":
    main()
