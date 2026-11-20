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

int service(int t, int duration) {
    if (!duration) return t;
    if (t%day == close) t = (t/day+1)*day+open;
    return t + duration + ((t%day-open+duration-1)/workday)*(day-workday);
}

struct Job { int src, dst, dispatch, last, support; Wide weight; };
struct Hold { int node, cargo; };
struct Step { int node, load, unload, hold; };
struct Search {
    int id, n, m, trucks, all, dispatches = 0, last_unloads = 0;
    Wide scale;
    std::array<Wide, masks> weight{};
    int dist[max_nodes][max_nodes], shortest[max_nodes][max_nodes];
    int loading[max_nodes]{}, unloading[max_nodes]{}, visits[max_nodes]{};
    bool home[max_nodes]{};
    std::vector<Job> jobs;
    std::vector<Step> trace;
    std::array<Hold, max_nodes> stack{};

    int ceil_trucks(Wide quantity) const { return int((quantity+scale-1)/scale); }

    void walk(int node, int t, int km, Wide numerator, int loaded, int unloaded,
              int stored, int reserved, int depth) {
        int mobile = loaded & ~unloaded & ~stored;
        int work = 0;
        int travel = shortest[node][0];
        for (int w=1; w<n; ++w) {
            int in = loading[w] & ~loaded, out = unloading[w] & ~unloaded;
            if (!(in || out)) continue;
            work += 600*(ceil_trucks(weight[in])+ceil_trucks(weight[out]));
            travel = std::max(travel, shortest[node][w]+shortest[w][0]);
        }
        int optimistic_day = service(t,work+24*travel)/day+1;
        if (optimistic_day > 91 || km+travel > 2000) return;

        for (int next=0; next<n; ++next) {
            if (next==node || (next && visits[next]==2)) continue;
            int mileage = km+dist[node][next];
            if (mileage+shortest[next][0] > 2000) continue;
            int km_leg = dist[node][next];
            int arrival = arrive(t,km_leg);
            Wide cost = numerator+weight[mobile]*dist[node][next];
            if (!next && unloaded==all && !depth) {
                std::cout << id << ' ' << arrival/day+1 << ' ' << decimal(cost) << ' ' << decimal(weight[all]) << ' ' << mileage;
                for (auto step : trace)
                    std::cout << ' ' << step.node << ':' << step.load << ':' << step.unload << ':' << step.hold;
                std::cout << " 0:0:0:0\n";
                continue;
            }
            if (!next) continue;
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
                    bool can_work = finish/day < 91 && (in || out || rejoin.cargo);
                    int on_board = ((loaded | in) & ~(unloaded | out) & ~new_stored);
                    int may_park = in && visits[next]==1 ? on_board : 0;
                    for (int park=may_park; can_work; park=0) {
                        int cars = park ? ceil_trucks(weight[park]) : 0;
                        if (weight[on_board & ~park] <= (trucks-new_reserved-cars)*scale) {
                            if (park) stack[new_depth]={next,park};
                            trace.push_back({next,in,out,park});
                            walk(next,finish,mileage,cost,loaded|in,unloaded|out,
                                 new_stored|park,new_reserved+cars,new_depth+bool(park));
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
    }
};

int main() {
    int cases;
    std::cin >> cases;
    while (cases--) {
        Search search{};

        search.run();
    }
}
