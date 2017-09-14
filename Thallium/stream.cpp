#include <vector>
#include <stdint.h>
#include <iostream>
#include <fstream>

class OutputStream;

class Serializable {
public:
    virtual void write(const OutputStream&) const = 0;
    virtual void read() = 0;
};

// https://github.com/telegramdesktop/tdesktop/blob/8f82880b938e06b7a2a27685ef9301edb12b4648/Telegram/SourceFiles/mtproto/core_types.h#L35
// Data is padded to 4 bytes so using an integer as the basic unit makes sense
using mtpPrime = int32_t;
using mtpBuffer = std::vector<mtpPrime>;

union int128_t {
    int32_t v[4];
};

union int256_t {
    int32_t v[8];
};

class OutputStream {
    mtpBuffer buffer;

public:
    OutputStream() {
    }

    // https://github.com/telegramdesktop/tdesktop/blob/8f82880b938e06b7a2a27685ef9301edb12b4648/Telegram/SourceFiles/mtproto/core_types.h#L315-L742
    OutputStream& operator<<(const int32_t &x) {
        buffer.push_back((mtpPrime)x);
        return *this;
    }

    OutputStream& operator<<(const int64_t &x) {
		buffer.push_back((mtpPrime)(x & 0xFFFFFFFFL));
        buffer.push_back((mtpPrime)(x >> 32));
        return *this;
    }

    OutputStream& operator<<(const int128_t &x) {
        buffer.push_back((mtpPrime)x.v[0]);
        buffer.push_back((mtpPrime)x.v[1]);
        buffer.push_back((mtpPrime)x.v[2]);
        buffer.push_back((mtpPrime)x.v[3]);
        return *this;
    }

    OutputStream& operator<<(const int256_t &x) {
        buffer.push_back((mtpPrime)x.v[0]);
        buffer.push_back((mtpPrime)x.v[1]);
        buffer.push_back((mtpPrime)x.v[2]);
        buffer.push_back((mtpPrime)x.v[3]);
        buffer.push_back((mtpPrime)x.v[4]);
        buffer.push_back((mtpPrime)x.v[5]);
        buffer.push_back((mtpPrime)x.v[6]);
        buffer.push_back((mtpPrime)x.v[7]);
        return *this;
    }

    OutputStream& operator<<(const double &x) {
        uint64_t i = *(uint64_t*)(&x);
		buffer.push_back((mtpPrime)(i & 0xFFFFFFFFL));
        buffer.push_back((mtpPrime)(i >> 32));
        return *this;
    }

    OutputStream& operator<<(const Serializable &x) {
        x.write(*this);
        return *this;
    }

    // https://github.com/telegramdesktop/tdesktop/blob/08167a6a91d4e672b40ce5d4a4d50ef8fa078bd4/Telegram/SourceFiles/mtproto/connection_tcp.cpp#L308
    char *getData() {
        return reinterpret_cast<char*>(&buffer[0]);
    }

    size_t size() {
        return static_cast<size_t>(buffer.size() * sizeof(mtpPrime));
    }
};

int main() {
    OutputStream out;
    int64_t constructor = 0x60469778;
    int128_t random = {1234, 5678};
    out << constructor;
    out << random;
    std::ofstream fout("reqpq.bin", std::ios::binary | std::ios::out);
    if (fout.is_open()) {
        fout.write(out.getData(), out.size());
    }
}
