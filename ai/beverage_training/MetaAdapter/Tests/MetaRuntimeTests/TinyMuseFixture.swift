import Foundation
import MLXVLM

enum TinyMuseFixture {
  static func configuration() throws -> MuseGlimmerConfiguration {
    let configJSON =
      #"{"model_type":"muse_glimmer","image_token_id":12,"video_token_id":13,"out_hidden_size":32,"projector_hidden_size":8,"text_config":{"vocab_size":32,"hidden_size":8,"intermediate_size":16,"num_hidden_layers":2,"num_attention_heads":2,"num_key_value_heads":1,"head_dim":4,"sliding_window":32},"vision_config":{"hidden_size":8,"intermediate_size":16,"num_hidden_layers":1,"num_attention_heads":2,"patch_size":2,"patch_temporal":1,"merge_size":2,"pos_emb_height":2,"pos_emb_width":2}}"#
    return try JSONDecoder().decode(
      MuseGlimmerConfiguration.self, from: Data(configJSON.utf8))
  }
}
