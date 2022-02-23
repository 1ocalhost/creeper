Vue.component('check-opt', {
  template: `
    <label>
      <input
        type="checkbox"
        :checked="getValue()"
        @input="e => setValue(e.target.checked)"
        :disabled="!loaded || pending"
        @change="onChanged($event)"
      />
      {{label}}
      <slot></slot>
    </label>
  `,
  props: {
    keyName: String,
    label: String,
    value: Boolean, /* (v-model) */
    loaded: {
      type: Boolean,
      default: true,
    },
    confirm: Object,
  },
  data() {
    return {
      pending: false,
    }
  },
  methods: {
    getValue() {
      return this.value;
    },
    setValue(checked) {
      this.$emit('input', checked);
    },
    doConfirm(isChecked) {
      const confirmInfo = this.confirm;
      if (!confirmInfo) {
        return true;
      }

      if (isChecked && confirmInfo.beforeCheck) {
        return confirm(confirmInfo.beforeCheck);
      } else if (!isChecked && confirmInfo.beforeUncheck) {
        return confirm(confirmInfo.beforeUncheck);
      }

      return true;
    },
    async onChanged(event) {
      this.pending = true;
      const isChecked = this.getValue();

      this.update(!isChecked);
      this.syncUi(event);

      if (!this.doConfirm(isChecked)) {
        return;
      }

      conf = {key: this.keyName, value: isChecked};
      result = await this.$root.apiPostJSON(
        '/api/user_settings', conf);
      if (result !== null) {
        this.update(isChecked);
      }
    },
    syncUi(event) {
      event.target.checked = this.getValue();
    },
    update(checked) {
      if (checked !== undefined) {
        this.setValue(!!checked);
        this.pending = false;
      }
    },
  },
});

Vue.component('user-settings-option', {
  template: `
    <check-opt
      v-model="$root.userSettings[keyName]"
      :loaded="$root.userSettingsLoaded"
      :key-name="keyName"
      :label="label"
      :confirm="confirm">
      <slot></slot>
    </check-opt>
  `,
  props: ['keyName', 'label', 'confirm'],
});

Vue.component('server-list', {
  template: `
    <div class="server-list" :hidden="feedData.hidden">
      <div class="feed-info card">
        <div class="feed-url-wrapper">
          <a v-if="scheme" class="text-tag" :scheme="scheme">{{scheme}}</a>
          <input type="text" v-model="feedData.url" :title="feedData.url" readonly />
          <div class="feed-updated">
            <a>{{serversUpdateTip}}</a>
          </div>
        </div>
        <div class="feed-op-buttons">
          <div style="margin-right: 15px;">
            <label :disabled="!duplicateNumber">
              <input type="checkbox" v-model="showDuplicate" :disabled="!duplicateNumber" />
                Duplicates ({{duplicateNumber}})
            </label>
            <label><input type="checkbox" v-model="showExtraInfo" />Details</label>
            <check-opt
              v-model="feedData.hidden"
              :loaded="true"
              :key-name="'hide_feed:' + feedData.uid"
              label="Hidden"
            >
            </check-opt>
          </div>
          <div>
            <button @click="editFeedUrl()">Edit</button>
            <button @click="$emit('delete-feed', feedData)" style="color: #e80c0c;">Remove</button>
            <button :disabled="!feedData.url || isUpdatingFeed" @click="emitUpdateFeed()">
              {{isUpdatingFeed ? 'Updating' : 'Update'}}
            </button>
            <button @click="testAllNodesOrStop()">
              {{isTestingSpeed ? 'Stop Test' : 'Test'}}
            </button>
          </div>
        </div>
      </div>
      <div v-if="feedData.proxies.length" class="card">
        <table :class="{'core-content-only': !showExtraInfo}">
          <thead>
            <tr>
              <th>Server</th>
              <th>Speed</th>
              <th>Operation</th>
            </tr>
          </thead>
          <tr v-for="(item, index) in feedData.proxies"
            :class="serverItemClass(item)"
            v-show="showDuplicate || !item.duplicate">
            <td>
              <a>{{item.conf.remark}}</a><br />
              <a class="extra-info">{{item.uid}}</a>
            </td>
            <td>
              <a :title="getNodeSpeed(item)?.title" :style="speedStyle(item)">
                {{speedText(item)}}
              </a><br />
              <a class="extra-info">{{getNodeSpeed(item)?.update}}</a>
            </td>
            <td>
              <span v-if="canTestSpeed(item, index)">
                <button @click="emitTestNode(item)">Test</button>
                <button @click="$emit('switch-node', item)">Switch</button>
                <button @click.prevent.stop="showMenu($event, item)">...</button>
              </span>
            </td>
          </tr>
        </table>
      </div>
      </div>
    </div>
  `,
  props: ['feedData'],
  data() {
    return {
      showDuplicate: false,
      showExtraInfo: false,
      isUpdatingFeed: false,
      isTestingSpeed: false,
    }
  },
  computed: {
    duplicateNumber() {
      return this.feedData.proxies.filter(
        item => item.duplicate
      ).length;
    },
    serversUpdateTip() {
      const updatedTime = this.feedData.update;
      if (updatedTime) {
        const interval = timeDiffFromNow(updatedTime);
        return `(updated ${interval})`;
      }
      return '';
    },
    scheme() {
      return this.feedData.scheme;
    },
  },
  methods: {
    async editFeedUrl() {
      const feedUrl = this.feedData.url;
      const url = promptURL('Edit Feed URL', feedUrl);
      if (url === null) {
        return;
      }

      this.$emit('edit-feed', this.feedData.uid, url, (result) => {
        if (result !== null) {
          this.feedData.url = url;
        }
      });
    },
    serverItemClass(item) {
      if (item.duplicate) {
        return {duplicate: true};
      }

      const activedServer = this.$parent.activedServer;
      const actived = (activedServer && item.uid === activedServer);
      return {
        actived,
        testing: item.testing,
      };
    },
    canTestSpeed(item, index) {
      if (item.conf.server_port === undefined) {
        return false;
      }

      if (item.duplicate) {
        return false;
      }

      if (isSpecialItem(item, index)) {
        return false;
      }

      return true;
    },
    getNodeSpeed(item) {
      if (item.testing) {
        return {
          update: '...',
          result: '\uD83C\uDFCD\uFE0F Testing...',
        };
      }
      return this.$parent.speed[item.uid];
    },
    speedText(item) {
      if (item.duplicate) {
        return;
      }
      return this.getNodeSpeed(item)?.result;
    },
    speedStyle(item) {
      const highestSpeed = this.$parent.highestSpeed;
      const speed = this.getNodeSpeed(item)?.speedNum;
      if (speed === null || speed === undefined || !highestSpeed) {
        return {
          'color': '#c5ae08',
        };
      }

      const colorSlow = [11, 75, 215];
      const colorFast = [255, 0, 191];

      let rgb = [];
      for (var i = 0; i < 3; ++i) {
        const colorDiff = colorFast[i] - colorSlow[i];
        rgb[i] = colorDiff * (speed / highestSpeed) + colorSlow[i];
      }

      return {
        'color': `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`,
      };
    },
    async testAllNodesOrStop() {
      if (this.isTestingSpeed) {
        this.isTestingSpeed = false;
        return;
      }

      this.isTestingSpeed = true;
      const proxies = this.feedData.proxies;
      for (const [index, proxy] of proxies.entries()) {
        if (!this.isTestingSpeed || !this.canTestSpeed(proxy, index)) {
          continue;
        }
        await new Promise(resolve => this.emitTestNode(proxy, resolve));
      }
      this.isTestingSpeed = false;
    },
    emitTestNode(item, callback) {
      item.testing = true;
      this.$emit('test-node', item, () => {
        item.testing = false;
        if (callback) {
          callback();
        }
      });
    },
    emitUpdateFeed() {
      this.isUpdatingFeed = true;
      this.$emit('update-feed', this.feedData.uid, (result) => {
        this.isUpdatingFeed = false;
      });
    },
    showMenu(event, item) {
      this.$parent.$refs.popupMenu.showMenu(event, item);
    },
  },
});
