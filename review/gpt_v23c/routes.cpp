// Exact integer ticks and equivalent-load arithmetic for isolated replay.
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

using Wide = __int128_t;
constexpr int day = 36000, open = 12000, close = 24000, workday = 12000;
constexpr int masks = 256, max_nodes = 10;

Wide read_wide() {
    std::string value;
    std::cin >> value;
    Wide result = 0;
    for (char digit : value) result = 10*result + (digit-'0');
    return result;
}

std::string decimal(Wide value) {
    if (value == 0) return "0";
    std::string result;
    for (; value; value /= 10) result += char('0' + value%10);
    std::reverse(result.begin(), result.end());
    return result;
}

int depart(int t, int km) {
    int today = t/day, phase = t%day;
    if (km > 500) return (today+(phase>open))*day+open;
    return phase+24*km <= close ? t : (today+1)*day+open;
}

int arrive(int t, int km) {
    int duration = 24*km;
    return depart(t,km)+duration+((duration-1)/workday)*(day-workday);
}

bool too_long(int since, int resume) {
    int idle = 0;
    for (int d=since/day; d<=resume/day; ++d)
        if (since <= d*day+open && resume >= d*day+close) ++idle;
    return idle > 1;
}

int service(int t, int duration) {
    if (!duration) return t;
    if (t%day == close) t = (t/day+1)*day+open;
    return t + duration + ((t%day-open+duration-1)/workday)*(day-workday);
}

struct Job { int src, dst, dispatch, last, support; Wide weight; };
struct Hold { int node, cargo, since; };
struct Step { int node, load, unload, hold; };
struct Label {
    Wide numerator = -1;
    int km = 0;
    std::vector<Step> trace;
};

struct Search {
    int id, n, m, trucks, all, mandatory = 0, dispatches = 0, last_unloads = 0;
    bool enforce_idle;
    Wide scale;
    std::array<Wide, masks> weight{};
    int dist[max_nodes][max_nodes], shortest[max_nodes][max_nodes];
    int loading[max_nodes]{}, unloading[max_nodes]{}, visits[max_nodes]{};
    bool home[max_nodes]{};
    std::vector<Job> jobs;
    std::vector<Step> trace;
    std::array<Hold, max_nodes> stack{};
    std::array<Label, 92> labels{};

    int ceil_trucks(Wide quantity) const { return int((quantity+scale-1)/scale); }

    bool covered(Wide estimate, int estimate_days) const {
        for (int d=1; d<=estimate_days; ++d) {
            if (labels[d].numerator >= 0 && labels[d].numerator < estimate) return true;
        }
        return false;
    }

    void walk(int node, int t, int km, Wide numerator, int loaded, int unloaded,
              int stored, int reserved, int depth, int pending_hold = -1) {
        int mobile = loaded & ~unloaded & ~stored;
        Wide estimate = numerator;
        for (int j=0; j<m; ++j) {
            int bit = 1<<j;
            if (unloaded & bit) continue;
            auto job = jobs[j];
            int from = node;
            if (!(loaded & bit)) from = job.src;
            if (stored & bit) {
                for (int k=0; k<depth; ++k)
                    if (stack[k].cargo & bit) from = stack[k].node;
            }
            estimate += weight[bit]*shortest[from][job.dst];
        }
        int work = 0;
        int travel = shortest[node][0];
        for (int w=1; w<n; ++w) {
            int in = loading[w] & ~loaded, out = unloading[w] & ~unloaded;
            if (!(in || out)) continue;
            work += 600*(ceil_trucks(weight[in])+ceil_trucks(weight[out]));
            travel = std::max(travel, shortest[node][w]+shortest[w][0]);
        }
        int optimistic_day = service(t,work+24*travel)/day+1;
        if (optimistic_day > 91 || km+travel > 2000 || covered(estimate,optimistic_day)) return;

        for (int next=0; next<n; ++next) {
            if (next==node || (next && visits[next]==2)) continue;
            int mileage = km+dist[node][next];
            if (mileage+shortest[next][0] > 2000) continue;
            int km_leg = dist[node][next];
            if (enforce_idle && pending_hold >= 0 && too_long(pending_hold,depart(t,km_leg))) continue;
            int arrival = arrive(t,km_leg);
            Wide cost = numerator+weight[mobile]*dist[node][next];
            if (!next && unloaded==all && !depth) {
                auto& label=labels[arrival/day+1];
                if (label.numerator<0 || cost<label.numerator ||
                    (cost==label.numerator && mileage<label.km)) {
                    label = {cost,mileage,trace};
                    label.trace.push_back({0,0,0,0});
                }
                // Further stops can arrive home sooner only via a different
                // path before this arrival, already explored separately.
                continue;
            }
            Hold rejoin{};
            int new_depth = depth, new_stored = stored, new_reserved = reserved;
            bool blocked = false;
            for (int i=0; i<depth; ++i) {
                if (stack[i].node != next) continue;
                if (i != depth-1) blocked = true;
                else rejoin = stack[i];
            }
            if (blocked) continue;
            if (rejoin.cargo) {
                --new_depth;
                new_stored &= ~rejoin.cargo;
                new_reserved -= ceil_trucks(weight[rejoin.cargo]);
            }
            int loads = loading[next] & ~loaded;
            int unloads = unloading[next] & loaded & ~unloaded & ~new_stored;
            for (int j=0; j<m; ++j)
                if ((loads & (1<<j)) && jobs[j].support && !(jobs[j].support & loaded))
                    loads &= ~(1<<j);
            if (!home[next] && ((dispatches & ~loaded) || (last_unloads & unloaded)))
                loads = unloads = 0;
            if (home[next]) {
                for (int w=1; w<n; ++w) {
                    if (!home[w] && ((loading[w] & ~loaded) || (unloading[w] & ~unloaded))) {
                        unloads &= ~last_unloads;
                        break;
                    }
                }
            }
            if (next) ++visits[next];
            for (int in=loads;; in=(in-1)&loads) {
                for (int out=unloads;; out=(out-1)&unloads) {
                    int minutes = 600*(ceil_trucks(weight[in])+ceil_trucks(weight[out]));
                    int finish = service(arrival,minutes);
                    bool can_work = finish/day < 91;
                    if (enforce_idle && rejoin.cargo && minutes) {
                        int resume = arrival%day == close ? (arrival/day+1)*day+open : arrival;
                        if (too_long(rejoin.since,resume)) can_work = false;
                    }
                    int on_board = ((loaded | in) & ~(unloaded | out) & ~new_stored);
                    int may_park = next && visits[next]==1 ? on_board : 0;
                    for (int park=may_park; can_work; park=(park-1)&may_park) {
                        int cars = park ? ceil_trucks(weight[park]) : 0;
                        if (weight[on_board & ~park] <= (trucks-new_reserved-cars)*scale) {
                            if (park) stack[new_depth]={next,park,finish};
                            trace.push_back({next,in,out,park});
                            walk(next,finish,mileage,cost,loaded|in,unloaded|out,
                                 new_stored|park,new_reserved+cars,new_depth+bool(park),
                                 rejoin.cargo && !minutes ? rejoin.since : -1);
                            trace.pop_back();
                            if (rejoin.cargo) stack[new_depth]=rejoin;
                        }
                        if (!park) break;
                    }
                    if (!out) break;
                }
                if (!in) break;
            }
            if (next) --visits[next];
        }
    }

    void run() {
        std::cin >> id >> n >> m >> trucks;
        scale = read_wide();
        all = (1<<m)-1;
        for (int i=0; i<n; ++i) std::cin >> home[i];
        for (int i=0; i<n; ++i)
            for (int j=0; j<n; ++j) {
                std::cin >> dist[i][j];
                shortest[i][j] = i==j ? 0 : dist[i][j];
            }
        for (int i=0; i<n; ++i)
            for (int j=0; j<n; ++j)
                for (int k=0; k<n; ++k)
                    shortest[j][k]=std::min(shortest[j][k],shortest[j][i]+shortest[i][k]);
        for (int i=0; i<m; ++i) {
            Job job{};
            std::cin >> job.src >> job.dst;
            job.weight = read_wide();
            std::cin >> job.dispatch >> job.last >> job.support;
            if (job.dispatch) dispatches |= 1<<i;
            if (job.last) last_unloads |= 1<<i;
            loading[job.src] |= 1<<i;
            unloading[job.dst] |= 1<<i;
            jobs.push_back(job);
        }
        for (int mask=1; mask<=all; ++mask) {
            int bit = __builtin_ctz(unsigned(mask));
            weight[mask] = jobs[bit].weight + weight[mask & (mask-1)];
        }
        walk(0,open,0,0,0,0,0,0,0);
        Wide best = -1;
        for (int d=1; d<=91; ++d) {
            auto& label = labels[d];
            if (label.numerator < 0 || (best >= 0 && best <= label.numerator)) continue;
            best = label.numerator;
            std::cout << id << ' ' << d << ' ' << decimal(best) << ' ' << decimal(weight[all])
                      << ' ' << label.km;
            for (auto step : label.trace)
                std::cout << ' ' << step.node << ':' << step.load << ':' << step.unload << ':' << step.hold;
            std::cout << '\n';
        }
    }
};

int main(int argc, char**) {
    int cases;
    std::cin >> cases;
    while (cases--) {
        Search search{};
        search.enforce_idle = argc > 1;
        search.run();
    }
}
