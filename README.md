# pd

a tool for interacting with pagerduty.

## setup

Get a personal pagerduty API key. Store it in `$HOME/.config/pd.json` like so:

``` json
{
    "api_key": "<your personal pagerduty api key>",
    "user_id": "<your user id - not required>"
}
```

You could also set it as the env variable `PAGERDUTY_API_KEY`, but keeping it in a file seems easier.
