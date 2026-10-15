"""Print spend from the local ledger and from OpenRouter's key endpoint, as a cross-check."""
from common import ledger
from common.llm import budget, key_usage


def main():
    print(f"Budget cap: ${budget():.2f}   Ledger total: ${ledger.total():.4f}")
    for field in ("component", "condition"):
        print(f"\nBy {field}:")
        for k, t in sorted(ledger.totals_by(field).items(), key=lambda kv: str(kv[0])):
            print(f"  {str(k):<18} ${t['cost_usd']:.4f}  {t['prompt_tokens']:>9} in  {t['completion_tokens']:>8} out  {t['calls']} calls")
    k = key_usage()
    print(f"\nOpenRouter key: usage ${k['usage']:.4f}, limit {k['limit']}")


if __name__ == "__main__":
    main()
