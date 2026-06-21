from hpsilab_mcp import HpsiMcpClient


def main() -> None:
    client = HpsiMcpClient()

    analysis = client.analyze_stock("NVDA")
    prediction = client.get_ai_prediction("NVDA")
    iv_radar = client.get_iv_radar("NVDA")
    option_pressure = client.get_option_pressure("NVDA")
    monte_carlo = client.get_monte_carlo("NVDA")
    equity_curves = client.get_equity_curves("NVDA")
    images = client.generate_stock_images("NVDA")
    report = client.generate_stock_research_report("NVDA")

    print("Analyze Stock:", analysis)
    print("AI Prediction:", prediction)
    print("IV Radar:", iv_radar)
    print("Option Pressure:", option_pressure)
    print("Monte Carlo:", monte_carlo)
    print("Equity Curves:", equity_curves)
    print("Stock Images:", images)
    print("Research Report:", report)


if __name__ == "__main__":
    main()
