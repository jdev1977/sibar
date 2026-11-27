**fetch.js**

```javascript
const fs = require("node:fs");
const axios = require("axios");
const cron = require("node-cron");

const apiKey = "<your-key>";

async function run() {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const { data } = await axios.get("https://api.example.com/data", { headers: { "X-Api-Key": apiKey } });
      fs.writeFileSync("data.json", JSON.stringify(data));
      return;
    } catch (error) {
      console.error(error.message);
    }
  }
}

cron.schedule("0 6 * * *", run);
```
