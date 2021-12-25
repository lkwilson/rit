from rit import pprint_time_duration

def test_pprint_time_duration():
  min = 60
  hour = 60 * min
  day = 24 * hour
  month = 32 * day # overestimate
  year = 370 * day # overestimate
  for i in [
    .5,
    .9,
    1,
    1.5,
    3,
    30,
    min,
    2 * min,
    hour,
    3* hour,
    day,
    2* day,
    month,
    2 * month,
    year,
    2 * year,
    3 * year,
    10 * year,
    100 * year,
  ]:
    print(i, pprint_time_duration(0, i))
  # assert False
