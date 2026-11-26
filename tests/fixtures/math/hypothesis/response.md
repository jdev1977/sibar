We test H0: mu = 50 against H1: mu != 50.

First check normality with the Shapiro-Wilk test; the sample is small (n = 8).

mean = 409.4/8 = 51.175
s = sqrt(5.0950/7) = 0.8531
t = (51.175 - 50) / (s / sqrt(n)) = 3.895

The one-sample t-test gives a p-value of about 0.006, so we reject H0 at the 5% level.

You can confirm it in R:

```r
x <- c(50.8, 51.6, 49.7, 52.3, 51.1, 50.4, 52.0, 51.5)
shapiro.test(x)
t.test(x, mu = 50)
```
